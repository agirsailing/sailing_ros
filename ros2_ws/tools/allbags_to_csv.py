#!/usr/bin/env python3
"""Export every recorded topic to CSV, without topic or message presets."""

import argparse
import array
import csv
from contextlib import ExitStack
import json
from pathlib import Path
import re
import sys


def _to_builtin(value):
    """Convert ROS messages and numeric arrays to ordinary Python values."""
    if hasattr(value, 'get_fields_and_field_types'):
        return {name: _to_builtin(getattr(value, name))
                for name in value.get_fields_and_field_types()}
    if isinstance(value, dict):
        return {key: _to_builtin(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, array.array, bytes, bytearray)):
        return [_to_builtin(item) for item in value]
    if hasattr(value, 'tolist'):
        return _to_builtin(value.tolist())
    return value


def _flatten(value, prefix='', out=None):
    """Flatten nested fields; keep variable-length arrays in single JSON cells."""
    if out is None:
        out = {}
    if isinstance(value, dict):
        for name, item in value.items():
            _flatten(item, f'{prefix}.{name}' if prefix else name, out)
    else:
        out[prefix] = json.dumps(value, ensure_ascii=False) if isinstance(value, list) else value
    return out


def _message_fields(message):
    fields = _flatten(_to_builtin(message))
    if 'timestamp_ns' in fields:
        fields['message.timestamp_ns'] = fields.pop('timestamp_ns')
    return fields


def _topic_filename(topic, used):
    name = re.sub(r'[^A-Za-z0-9_.-]', '_', topic.strip('/')) or 'topic'
    if name.split('.')[0].upper() in {'CON', 'PRN', 'AUX', 'NUL',
                                     *(f'COM{i}' for i in range(1, 10)),
                                     *(f'LPT{i}' for i in range(1, 10))}:
        name = f'topic_{name}'
    candidate, suffix = name, 2
    while candidate.casefold() in used:
        candidate = f'{name}__{suffix}'
        suffix += 1
    used.add(candidate.casefold())
    return candidate + '.csv'


def process_single_bag(bag_path, output_root=None):
    # Lazy imports keep --help and helper tests independent of ROS.
    import rosbag2_py
    from rclpy.serialization import deserialize_message
    from rosidl_runtime_py.utilities import get_message

    bag_path = Path(bag_path)
    out_dir = Path(output_root or Path.cwd()) / bag_path.name.removeprefix('rosbag2_')
    if out_dir.resolve() == bag_path.resolve():
        raise ValueError('La cartella CSV non può coincidere con la bag: usa --output-dir.')
    reader = rosbag2_py.SequentialReader()
    reader.open(rosbag2_py.StorageOptions(uri=str(bag_path)),
                rosbag2_py.ConverterOptions('cdr', 'cdr'))
    topics = sorted(reader.get_all_topics_and_types(), key=lambda item: item.name)

    # Resolve every type first: never silently skip unavailable custom types.
    types, schemas = {}, {}
    for topic in topics:
        try:
            types[topic.name] = get_message(topic.type)
            schemas[topic.name] = list(_message_fields(types[topic.name]()))
        except Exception as error:
            raise RuntimeError(f'Tipo non disponibile: {topic.type} ({topic.name}). '
                               'Compila e carica il workspace che definisce il messaggio.') from error

    out_dir.mkdir(parents=True, exist_ok=True)
    writers, counts, filenames, used = {}, {}, {}, set()
    with ExitStack() as stack:
        for topic in topics:
            name = topic.name
            filenames[name] = _topic_filename(name, used)
            stream = stack.enter_context((out_dir / filenames[name]).open(
                'w', encoding='utf-8', newline=''))
            writers[name] = csv.DictWriter(stream, fieldnames=['timestamp_ns', *schemas[name]])
            writers[name].writeheader()
            counts[name] = 0
        while reader.has_next():
            name, raw, timestamp = reader.read_next()
            message = deserialize_message(raw, types[name])
            writers[name].writerow({'timestamp_ns': timestamp, **_message_fields(message)})
            counts[name] += 1
    for name in counts:
        print(f'  {name} -> {out_dir / filenames[name]} ({counts[name]} righe)')
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('parent_folder', type=Path,
                        help='Cartella delle bag oppure una singola bag con metadata.yaml')
    parser.add_argument('--output-dir', type=Path, default=Path.cwd(),
                        help='Cartella padre dei CSV (default: directory corrente)')
    args = parser.parse_args(argv)
    parent = args.parent_folder.resolve()
    if not parent.is_dir():
        parser.error(f'Cartella inesistente: {parent}')
    bags = ([parent] if (parent / 'metadata.yaml').is_file() else sorted(
        path for path in parent.iterdir() if path.is_dir() and (
            (path / 'metadata.yaml').is_file() or path.name.startswith('rosbag2_'))))
    if not bags:
        parser.error(f'Nessuna rosbag trovata in {parent}')
    names = [path.name.removeprefix('rosbag2_').casefold() for path in bags]
    if len(names) != len(set(names)):
        parser.error('Nomi delle cartelle CSV duplicati: esporta le bag separatamente.')
    failures = 0
    for bag in bags:
        print(f'Esportazione: {bag.name}')
        try:
            process_single_bag(bag, args.output_dir)
        except Exception as error:
            failures += 1
            print(f'ERRORE {bag.name}: {error}. Eventuali CSV parziali non sono completi.', file=sys.stderr)
    print(f'Bag completate: {len(bags) - failures}/{len(bags)}')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())
