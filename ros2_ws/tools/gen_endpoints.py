#!/usr/bin/env python3

import yaml
from pathlib import Path
import sys
from typing import Any, Dict

ROOT = Path(__file__).resolve().parents[1]  # ros2_ws
SRC = ROOT / "src"


def die(msg: str):
    print(f"[gen_endpoints] ❌ {msg}")
    sys.exit(1)


def resolve_ref(value, mapping):
    """Resolve '@key' in a mapping (topics/services)."""
    if isinstance(value, str) and value.startswith("@"):
        key = value[1:]
        if key not in mapping:
            die(f"Reference '@{key}' not found")
        return mapping[key]
    return value


def _resolve_nested_refs(obj: Any, mapping: Dict[str, str]) -> Any:
    """
    Recursively resolve '@key' references inside nested dicts/lists/strings.
    """
    if isinstance(obj, dict):
        return {k: _resolve_nested_refs(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_nested_refs(v, mapping) for v in obj]
    return resolve_ref(obj, mapping)


def generate_python(pkg_name, pkg_dir, topics, services, nodes):
    py_pkg_dir = pkg_dir / pkg_name / "generated"
    py_pkg_dir.mkdir(parents=True, exist_ok=True)

    (py_pkg_dir / "__init__.py").touch(exist_ok=True)
    out = py_pkg_dir / "ros_endpoints.py"

    lines = []
    lines.append("# AUTO-GENERATED FILE. DO NOT EDIT.\n")

    # -------- Topics --------
    lines.append("class Topics:")

    # Shared (keep it: contains raw topic registry; optional but handy)
    if topics:
        lines.append("    class Shared:")
        for k, v in topics.items():
            lines.append(f"        {k.upper()} = {v!r}")
    else:
        lines.append("    class Shared:")
        lines.append("        pass")

    # Per-node (ROS sub/pub + MQTT sub/pub/rsp)
    for node, data in nodes.items():
        cls = node.upper()
        lines.append(f"\n    class {cls}:")
        wrote_any = False

        # ROS directions
        for direction in ("sub", "pub"):
            if direction in data:
                if wrote_any:
                    lines.append("")
                wrote_any = True
                block = data.get(direction) or {}
                lines.append(f"        class {direction.upper()}:")
                if block:
                    for name, topic in block.items():
                        lines.append(f"            {name.upper()} = {topic!r}")
                else:
                    lines.append("            pass")

        # MQTT block
        mqtt_block = data.get("mqtt")
        if mqtt_block is not None:
            if wrote_any:
                lines.append("")
            wrote_any = True
            lines.append("        class MQTT:")
            # support mqtt as dict with optional sub/pub/rsp
            for mdir in ("sub", "pub", "rsp"):
                m = (mqtt_block.get(mdir) or {}) if isinstance(mqtt_block, dict) else {}
                if mdir != "sub":
                    lines.append("")
                lines.append(f"            class {mdir.upper()}:")
                if m:
                    for name, topic in m.items():
                        lines.append(f"                {name.upper()} = {topic!r}")
                else:
                    lines.append("                pass")

        if not wrote_any:
            lines.append("        pass")

    # -------- Services (only if needed) --------
    any_node_has_srv = any(("srv" in nd and nd["srv"]) for nd in nodes.values())
    if services or any_node_has_srv:
        lines.append("\n\nclass Services:")

        # Shared
        if services:
            lines.append("    class Shared:")
            for k, v in services.items():
                lines.append(f"        {k.upper()} = {v!r}")
        else:
            lines.append("    class Shared:")
            lines.append("        pass")

        # Per-node SRV
        for node, data in nodes.items():
            cls = node.upper()
            lines.append(f"\n    class {cls}:")
            if "srv" in data and data["srv"]:
                lines.append("        class SRV:")
                for name, srv in data["srv"].items():
                    lines.append(f"            {name.upper()} = {srv!r}")
            else:
                lines.append("        pass")

    out.write_text("\n".join(lines) + "\n")
    print(f"[gen_endpoints] 🐍 Generated Python endpoints for {pkg_name}")


def generate_cpp(pkg_name, pkg_dir, topics, services, nodes):
    inc_dir = pkg_dir / "include" / pkg_name
    inc_dir.mkdir(parents=True, exist_ok=True)

    out = inc_dir / "ros_endpoints.hpp"
    guard = f"{pkg_name.upper()}_ROS_ENDPOINTS_HPP"

    lines = []
    lines.append("// AUTO-GENERATED FILE. DO NOT EDIT.")
    lines.append(f"#ifndef {guard}")
    lines.append(f"#define {guard}\n")
    lines.append("namespace ros_endpoints {\n")

    # SharedTopics
    lines.append("struct SharedTopics {")
    if topics:
        for k, v in topics.items():
            lines.append(f"  static constexpr const char* {k.upper()} = \"{v}\";")
    lines.append("};\n")

    # SharedServices
    lines.append("struct SharedServices {")
    if services:
        for k, v in services.items():
            lines.append(f"  static constexpr const char* {k.upper()} = \"{v}\";")
    lines.append("};\n")

    # Backward-compatible alias: Shared == SharedTopics
    lines.append("using Shared = SharedTopics;\n")

    # Per-node structs
    for node, data in nodes.items():
        struct = node.upper()
        lines.append(f"struct {struct} {{")

        # ROS sub/pub
        for direction in ("sub", "pub"):
            if direction in data:
                lines.append(f"  struct {direction.upper()} {{")
                block = data.get(direction) or {}
                if block:
                    for name, topic in block.items():
                        lines.append(f"    static constexpr const char* {name.upper()} = \"{topic}\";")
                lines.append("  };")

        # MQTT sub/pub/rsp
        mqtt_block = data.get("mqtt")
        if isinstance(mqtt_block, dict):
            lines.append("  struct MQTT {")
            for mdir in ("sub", "pub", "rsp"):
                m = mqtt_block.get(mdir) or {}
                lines.append(f"    struct {mdir.upper()} {{")
                if m:
                    for name, topic in m.items():
                        lines.append(f"      static constexpr const char* {name.upper()} = \"{topic}\";")
                lines.append("    };")
            lines.append("  };")

        # SRV per-node
        if "srv" in data and data["srv"]:
            lines.append("  struct SRV {")
            for name, srv in data["srv"].items():
                lines.append(f"    static constexpr const char* {name.upper()} = \"{srv}\";")
            lines.append("  };")

        lines.append("};\n")

    lines.append("} // namespace ros_endpoints\n")
    lines.append(f"#endif // {guard}\n")

    out.write_text("\n".join(lines))
    print(f"[gen_endpoints] ⚙️ Generated C++ endpoints for {pkg_name}")


def main():
    yamls = list(SRC.glob("**/config/endpoints.yaml"))

    if not yamls:
        print("[gen_endpoints] ⚠️ No endpoints.yaml found")
        return

    for yml in yamls:
        pkg_dir = yml.parents[1]
        pkg_name = pkg_dir.name

        data = yaml.safe_load(yml.read_text())

        meta = data.get("meta", {})
        gen = meta.get("generate", {})
        gen_py = bool(gen.get("python", False))
        gen_cpp = bool(gen.get("cpp", False))

        if not (gen_py or gen_cpp):
            print(f"[gen_endpoints] ⏭️  {pkg_name}: generation disabled")
            continue

        topics_raw = data.get("topics", {}) or {}
        services_raw = data.get("services", {}) or {}
        nodes_raw = data.get("nodes", {}) or {}

        # Resolve top-level registries
        topics = {k: resolve_ref(v, topics_raw) for k, v in topics_raw.items()}
        services = {k: resolve_ref(v, services_raw) for k, v in services_raw.items()}

        # Resolve nodes (ROS sub/pub, SRV, MQTT nested)
        nodes = {}
        for node, nd in nodes_raw.items():
            nodes[node] = {}

            for direction in ("sub", "pub"):
                if direction in nd:
                    nodes[node][direction] = {
                        k: resolve_ref(v, topics) for k, v in (nd[direction] or {}).items()
                    }

            if "srv" in nd:
                nodes[node]["srv"] = {
                    k: resolve_ref(v, services) for k, v in (nd["srv"] or {}).items()
                }

            if "mqtt" in nd:
                # mqtt is nested: resolve against topics registry
                nodes[node]["mqtt"] = _resolve_nested_refs(nd["mqtt"], topics)

        if gen_py:
            generate_python(pkg_name, pkg_dir, topics, services, nodes)
        if gen_cpp:
            generate_cpp(pkg_name, pkg_dir, topics, services, nodes)


if __name__ == "__main__":
    main()
