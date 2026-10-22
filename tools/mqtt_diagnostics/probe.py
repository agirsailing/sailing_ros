"""Standalone synthetic boat + native/WebSocket MQTT observers. No ROS needed."""

import argparse
import csv
from datetime import datetime, timezone
import getpass
import json
import math
import os
from pathlib import Path
import statistics
import threading
import time
import uuid


def utc():
    return datetime.now(timezone.utc).isoformat()


def payload(kind, elapsed, run_id, sequence, decimals=None, ultrasonic_pattern='step'):
    stamp_ns = time.time_ns()
    stamp = dict(sec=stamp_ns // 10**9, nanosec=stamp_ns % 10**9)
    header = dict(stamp=stamp, frame_id='')
    wave = math.sin(elapsed)
    distance = 0.5 if int(elapsed // 5) % 2 == 0 else 0.8
    if ultrasonic_pattern == 'ramp':
        # Sequence-based triangle: every message changes by 2 cm, including turns.
        # Its period is 30 dashboard messages, not a fixed physical wave period.
        phase = (sequence - 1) % 30
        distance = 0.5 + 0.02 * (phase if phase <= 15 else 30 - phase)
    if kind == 'dashboard':
        data = dict(header=header, attitude_valid=True, roll_deg=12 + wave,
                    pitch_deg=wave, yaw_deg=32 + wave, height_valid=True,
                    height_m=distance - 0.2, battery_valid=True, battery_low=False,
                    battery_voltage_v=12.4, sog_valid=True, sog_mps=6.0,
                    ultrasonic_left_valid=True, ultrasonic_left_m=distance + 0.0000000238418579,
                    ultrasonic_right_valid=True, ultrasonic_right_m=distance + 0.03)
    elif kind == 'map':
        data = dict(header=header, gps_stamp=stamp, fix_valid=True,
                    latitude_deg=59.3293 + 0.002 * math.sin(elapsed / 60),
                    longitude_deg=18.0686 + 0.002 * math.cos(elapsed / 60), sog_mps=6.0)
    else:
        data = dict(recording=False, bag_name='', last_error='')
    # Round only dashboard floating-point fields, never coordinates or timestamps.
    if decimals is not None and kind == 'dashboard':
        data = {key: round(value, decimals) if isinstance(value, float) else value
                for key, value in data.items()}
    data['_probe'] = dict(run_id=run_id, sequence=sequence, sent_ns=time.perf_counter_ns())
    return json.dumps(data, allow_nan=False, separators=(',', ':'))


def load_config(path, ros_config=None):
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    base = config['publisher']
    if ros_config:
        import yaml
        params = yaml.safe_load(Path(ros_config).read_text(encoding='utf-8'))
        mqtt = params['telemetry_gateway_node']['ros__parameters']['mqtt']
        base.update(host=mqtt['broker'], port=mqtt['port'], tls=mqtt['tls_enabled'],
                    username=mqtt['user'], password=mqtt['password'], ca_file=mqtt.get('ca_file', ''))
    cache = {}
    def credentials(endpoint):
        for field in ('username', 'password'):
            env = endpoint.get(field + '_env')
            if field not in endpoint and env:
                if env not in cache:
                    value = os.environ.get(env)
                    if value is None:
                        value = getpass.getpass(f'{env} (hidden): ') if field == 'password' else input(f'{env}: ')
                    cache[env] = value
                endpoint[field] = cache[env]
        return endpoint
    publisher = credentials(dict(base))
    subscribers = []
    for override in config['subscribers']:
        endpoint = {**base, **override}
        # Explicit subscriber credential variables override inherited boat credentials.
        for field in ('username', 'password'):
            if field + '_env' in override:
                endpoint.pop(field, None)
        subscribers.append(credentials(endpoint))
    names = [item['name'] for item in subscribers]
    if not names or len(set(names)) != len(names) or 'publisher' in names:
        raise ValueError('Subscriber names must be unique and different from publisher')
    for endpoint in [publisher, *subscribers]:
        if not endpoint.get('host') or 'REPLACE' in endpoint['host']:
            raise ValueError('Set the broker host, or use --ros-config')
        if endpoint.get('transport', 'tcp') not in ('tcp', 'websockets'):
            raise ValueError('Transport must be tcp or websockets')
    return publisher, subscribers


class Recorder:
    def __init__(self, directory):
        self.directory = directory
        self.lock = threading.RLock()
        self.started = time.perf_counter()
        self.events = (directory / 'events.jsonl').open('w', encoding='utf-8')
        self.samples = (directory / 'samples.csv').open('w', newline='', encoding='utf-8')
        self.writer = csv.writer(self.samples)
        self.writer.writerow(['elapsed_s', 'observer', 'stream', 'sequence', 'latency_ms', 'bytes'])
        self.counts = {}

    def event(self, role, event, **details):
        with self.lock:
            self.counts[role + ':' + event] = self.counts.get(role + ':' + event, 0) + 1
            self.events.write(json.dumps(dict(utc=utc(), elapsed_s=time.perf_counter() - self.started,
                                             role=role, event=event, **details)) + '\n')
            self.events.flush()
        if event in ('connected', 'disconnected', 'connect_failed', 'subscription_rejected'):
            print(f'{utc()} {role}: {event} {details}', flush=True)

    def sample(self, role, kind, meta, size):
        # All observers run in this process; monotonic latency has no PC/Pi clock offset.
        now_ns = time.perf_counter_ns()
        with self.lock:
            self.writer.writerow([round(time.perf_counter() - self.started, 6), role, kind,
                                  meta['sequence'], (now_ns - meta['sent_ns']) / 1e6, size])
            self.samples.flush()

    def close(self):
        self.events.close()
        self.samples.close()


class Peer:
    def __init__(self, role, endpoint, recorder, run_id, prefix, topics, qos, protocol):
        import paho.mqtt.client as mqtt
        self.role, self.recorder, self.run_id = role, recorder, run_id
        self.topics, self.prefix = topics, prefix
        self.connected = threading.Event()
        self.ready = threading.Event()
        self.stopping = False
        self.id = f'agir_probe_{role}_{run_id}'
        kwargs = dict(callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                      client_id=self.id, transport=endpoint.get('transport', 'tcp'),
                      protocol=mqtt.MQTTv5 if protocol == '5' else mqtt.MQTTv311)
        if protocol == '311':
            kwargs['clean_session'] = True
        self.client = mqtt.Client(**kwargs)
        self.client.connect_timeout = 10
        self.client.max_queued_messages_set(10)
        self.client.reconnect_delay_set(1, 10)
        if endpoint.get('username') or endpoint.get('password'):
            self.client.username_pw_set(endpoint.get('username', ''), endpoint.get('password', ''))
        if endpoint.get('tls', True):
            self.client.tls_set(ca_certs=endpoint.get('ca_file') or None)
        if endpoint.get('transport') == 'websockets':
            self.client.ws_set_options(path=endpoint.get('ws_path', '/mqtt'))

        def on_connect(client, userdata, flags, reason, properties):
            recorder.event(role, 'connected' if not reason.is_failure else 'connection_rejected',
                           client_id=self.id, code=reason.value, reason=str(reason))
            if reason.is_failure:
                return
            self.connected.set()
            if role != 'publisher':
                client.subscribe([(topic, qos) for topic in topics])
            else:
                self.ready.set()

        def on_subscribe(client, userdata, mid, reasons, properties):
            accepted = len(reasons) == len(topics) and all(not reason.is_failure for reason in reasons)
            recorder.event(role, 'subscribed' if accepted else 'subscription_rejected',
                           codes=[reason.value for reason in reasons])
            if accepted:
                self.ready.set()

        def on_disconnect(client, userdata, flags, reason, properties):
            self.connected.clear()
            self.ready.clear()
            recorder.event(role, 'disconnected', code=reason.value, reason=str(reason),
                           from_server=flags.is_disconnect_packet_from_server, expected=self.stopping)

        def on_message(client, userdata, message):
            if message.retain:
                return
            try:
                meta = json.loads(message.payload).get('_probe', {})
                if meta.get('run_id') != run_id:
                    return
                if not isinstance(meta.get('sequence'), int) or not isinstance(meta.get('sent_ns'), int):
                    return
                recorder.sample(role, message.topic.rsplit('/', 1)[-1], meta, len(message.payload))
            except (ValueError, TypeError, AttributeError):
                recorder.event(role, 'malformed_message')

        self.client.on_connect = on_connect
        self.client.on_subscribe = on_subscribe
        self.client.on_disconnect = on_disconnect
        self.client.on_message = on_message
        self.client.on_connect_fail = lambda *_: recorder.event(role, 'connect_failed')
        self.client.on_publish = lambda *_: recorder.event(role, 'publish_completed')
        # Keep only recognized ping events. Paho's unrestricted logs can contain usernames.
        self.client.on_log = lambda c, u, level, text: (
            recorder.event(role, 'ping_sent' if text == 'Sending PINGREQ' else 'ping_received')
            if text in ('Sending PINGREQ', 'Received PINGRESP') else None)
        self.endpoint = endpoint
        recorder.event(role, 'client_created', client_id=self.id,
                       transport=endpoint.get('transport', 'tcp'), tls=endpoint.get('tls', True))

    def start(self):
        self.client.connect_async(self.endpoint['host'], int(self.endpoint['port']), keepalive=60)
        self.client.loop_start()

    def stop(self):
        self.stopping = True
        self.client.disconnect()
        self.client.loop_stop()


def percentile(values, fraction):
    return sorted(values)[min(len(values) - 1, int((len(values) - 1) * fraction))] if values else None


def analyze(directory):
    directory = Path(directory)
    groups = {}
    with (directory / 'samples.csv').open(encoding='utf-8') as stream:
        for row in csv.DictReader(stream):
            groups.setdefault(row['observer'] + '/' + row['stream'], []).append(row)
    summary = dict(run=json.loads((directory / 'run.json').read_text(encoding='utf-8')),
                   streams={}, disconnects=[], publish_counts={}, failures=[])
    for line in (directory / 'events.jsonl').read_text(encoding='utf-8').splitlines():
        event = json.loads(line)
        if event['event'] == 'disconnected' and not event['expected']:
            summary['disconnects'].append(event)
        if event['event'] in ('connect_failed', 'connection_rejected', 'subscription_rejected', 'startup_timeout', 'fatal_error'):
            summary['failures'].append(event)
        if event['event'] == 'publish':
            kind = event['stream']
            counts = summary['publish_counts'].setdefault(kind, dict(attempts=0, accepted_by_client=0, skipped_offline=0))
            counts['attempts'] += 1
            counts['accepted_by_client'] += event['rc'] == 0
            counts['skipped_offline'] += event['rc'] is None
    for name, rows in groups.items():
        times = [float(row['elapsed_s']) for row in rows]
        latencies = [float(row['latency_ms']) for row in rows]
        sequences = [int(row['sequence']) for row in rows]
        first = [lat for t, lat in zip(times, latencies) if t <= times[0] + 60]
        last = [lat for t, lat in zip(times, latencies) if t >= times[-1] - 60]
        summary['streams'][name] = dict(
            received=len(rows), unique_sequences=len(set(sequences)),
            duplicates=len(rows) - len(set(sequences)),
            p50_ms=statistics.median(latencies), p95_ms=percentile(latencies, .95),
            max_ms=max(latencies), first_minute_p50_ms=statistics.median(first),
            last_minute_p50_ms=statistics.median(last),
            max_receive_gap_s=max((b - a for a, b in zip(times, times[1:])), default=0),
            observed_hz=(len(rows) - 1) / (times[-1] - times[0]) if times[-1] > times[0] else 0,
            mean_payload_bytes=statistics.mean(int(row['bytes']) for row in rows))
    (directory / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    lines = ['# MQTT diagnostic report', '',
             'Latency: synthetic publish call to Python observer callback, on one monotonic clock.',
             'Includes local scheduling and transport; does not measure browser rendering.',
             'Publish acceptance is not delivery. QoS 0 completion is not a broker acknowledgement.', '',
             f"Ultrasonic pattern: {summary['run'].get('ultrasonic_pattern', 'step')}.", '',
             f"Unexpected disconnects: {len(summary['disconnects'])}. Setup/errors: {len(summary['failures'])}.", '',
             '| Observer/stream | Received | Actual Hz | p50 ms | p95 ms | Max ms | First/last minute p50 ms | Max gap s |',
             '|---|---:|---:|---:|---:|---:|---:|---:|']
    for name, item in summary['streams'].items():
        lines.append(f"| {name} | {item['received']} | {item['observed_hz']:.2f} | {item['p50_ms']:.1f} | {item['p95_ms']:.1f} | "
                     f"{item['max_ms']:.1f} | {item['first_minute_p50_ms']:.1f} / {item['last_minute_p50_ms']:.1f} | "
                     f"{item['max_receive_gap_s']:.2f} |")
    if not groups:
        lines += ['', '**No matching probe messages received: this is not a successful test.**']
    lines += ['', 'Use events.jsonl to correlate UTC disconnects and reason codes with broker logs.',
              'MQTT 3.1.1 may report only a generic transport loss. MQTT 5 may provide more detail.',
              'Compare separate runs at identical rates and duration. Do not infer causation from a single run.',
              'Raw samples and event files can also be analyzed after an interrupted run.']
    (directory / 'report.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--analyze', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--ros-config', type=Path, help='Reuse local boat credentials; never copied into reports')
    parser.add_argument('--duration', type=float, default=900)
    parser.add_argument('--dashboard-hz', type=float, default=2)
    parser.add_argument('--map-hz', type=float, default=2)
    parser.add_argument('--state-hz', type=float, default=.5)
    parser.add_argument('--decimals', type=int, choices=range(0, 10))
    parser.add_argument('--ultrasonic-pattern', choices=['step', 'ramp'], default='step',
                        help='step: switch every 5 s; ramp: change by 2 cm every dashboard message')
    parser.add_argument('--protocol', choices=['311', '5'], default='311')
    parser.add_argument('--qos', type=int, choices=[0, 1], default=0)
    parser.add_argument('--webapp', action='store_true', help='Publish simulated data on agir_gui/data; stop real boat publishers first')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args(argv)
    if args.analyze:
        analyze(args.analyze)
        print(f'Report: {args.analyze / "report.md"}')
        return 0
    rates = dict(dashboard=args.dashboard_hz, map=args.map_hz, recording_state=args.state_hz)
    if not args.config:
        parser.error('--config is required')
    if not math.isfinite(args.duration) or not 0 < args.duration <= 7200:
        parser.error('--duration must be between 0 and 7200 seconds')
    if any(not math.isfinite(rate) or not 0 < rate <= 100 for rate in rates.values()):
        parser.error('Each frequency must be positive and at most 100 Hz')
    publisher_config, subscribers_config = load_config(args.config, args.ros_config)
    run_id = uuid.uuid4().hex[:12]
    prefix = 'agir_gui/data' if args.webapp else f'agir_diag/{run_id}'
    topics = [prefix + '/' + kind for kind in rates]
    directory = args.output or Path(__file__).parent / 'runs' / (datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + run_id)
    directory.mkdir(parents=True, exist_ok=False)
    # Explicit allowlist: never serialize configuration, environment or CLI secrets.
    metadata = dict(run_id=run_id, started_utc=utc(), rates_hz=rates,
                    planned_publish_per_s=sum(rates.values()), duration_s=args.duration,
                    protocol=args.protocol, qos=args.qos, decimals=args.decimals,
                    ultrasonic_pattern=args.ultrasonic_pattern,
                    clock_resolution_s=time.get_clock_info('perf_counter').resolution,
                    topic_prefix=prefix, observers=[cfg['name'] for cfg in subscribers_config])
    (directory / 'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    recorder = Recorder(directory)
    peers = []
    result = 0
    print(f'Output: {directory.resolve()}\nTopics: {prefix}/...\nTotal: {sum(rates.values())} publishes/s', flush=True)
    print(f'Ultrasonic pattern: {args.ultrasonic_pattern}', flush=True)
    try:
        publisher = Peer('publisher', publisher_config, recorder, run_id, prefix, topics, args.qos, args.protocol)
        peers.append(publisher)
        peers.extend(Peer(cfg['name'], cfg, recorder, run_id, prefix, topics, args.qos, args.protocol)
                     for cfg in subscribers_config)
        for peer in peers:
            peer.start()
        deadline = time.perf_counter() + 30
        while not all(peer.ready.is_set() for peer in peers):
            if time.perf_counter() >= deadline:
                recorder.event('test', 'startup_timeout', not_ready=[p.role for p in peers if not p.ready.is_set()])
                return 2
            time.sleep(.05)
        start = time.perf_counter()
        due = {kind: start for kind in rates}
        sequence = {kind: 0 for kind in rates}
        next_status = start + 10
        while time.perf_counter() - start < args.duration:
            now = time.perf_counter()
            for kind, rate in rates.items():
                if now < due[kind]:
                    continue
                sequence[kind] += 1
                data = payload(kind, now - start, run_id, sequence[kind], args.decimals,
                               args.ultrasonic_pattern)
                rc = None
                if publisher.connected.is_set():
                    rc = int(publisher.client.publish(prefix + '/' + kind, data, qos=args.qos, retain=False).rc)
                recorder.event('publisher', 'publish', stream=kind, sequence=sequence[kind],
                               rc=rc, bytes=len(data.encode('utf-8')))
                # Skip missed slots: never generate a catch-up burst after a stall/outage.
                next_due = due[kind] + 1 / rate
                due[kind] = next_due if next_due > now else now + 1 / rate
            if now >= next_status:
                print(f'{now - start:.0f}s: ' + ', '.join(f'{p.role}={"up" if p.ready.is_set() else "down"}' for p in peers), flush=True)
                next_status = now + 10
            time.sleep(min(.01, max(.001, min(due.values()) - time.perf_counter())))
        # Bounded drain; late/missing delivery remains visible in the report.
        time.sleep(2)
    except KeyboardInterrupt:
        recorder.event('test', 'interrupted')
        result = 130
    except Exception as error:
        recorder.event('test', 'fatal_error', exception_type=type(error).__name__)
        print(f'Test failed ({type(error).__name__}); check config and events.jsonl. Credentials are not logged.')
        result = 2
    finally:
        for peer in peers:
            peer.stop()
        recorder.close()
        summary = analyze(directory)
        print(f'Report: {directory.resolve() / "report.md"}', flush=True)
    if not summary['streams'] or summary['failures'] or summary['disconnects']:
        result = result or 2
    return result


if __name__ == '__main__':
    raise SystemExit(main())
