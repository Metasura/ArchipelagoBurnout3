"""Read-only Crash Mode memory probe for PCSX2 PINE.

Run from the repository root:
    .venv/bin/python -m worlds.burnout3.crash_memory_probe
"""

import argparse
import time

from .B3Client import EXPECTED_GAME_ID
from .pine import Pine


CRASH_SCORE_BASE = 0x0064D2C0
CRASH_SCORE_FIELDS = {
    "score": (0x0064E4BC, 4, "Current score"),
    "crash_damage": (0x0064E508, 4, "Current crash damage"),
    "vehicles_destroyed": (0x0064EAF8, 4, "Vehicles destroyed"),
    "crash_payout": (0x0064EB08, 4, "Current crash payout"),
}
OTHER_FIELDS = {
    "current_event": (0x01E901C8, 4, "True current event"),
    "crash_state": (0x0064EC9A, 1, "Crash state"),
    "in_game": (0x01D6E204, 1, "In game"),
    "score_bonus_event": (0x0064EABC, 4, "Burnout points earned"),
}


def read_fields(pine):
    values = {}
    for name, (address, width, _description) in {**CRASH_SCORE_FIELDS, **OTHER_FIELDS}.items():
        if width == 1:
            values[name] = pine.read_int8(address)
        elif width == 4:
            values[name] = pine.read_int32(address)
        else:
            raise ValueError(f"Unsupported field width: {width}")
    return values


def print_fields(values):
    for name, (_address, _width, description) in {**CRASH_SCORE_FIELDS, **OTHER_FIELDS}.items():
        print(f"{name:20} {values[name]:11d} (0x{values[name] & 0xFFFFFFFF:08X})  {description}")


def read_window(pine, start, length):
    data = pine.read_bytes(start, length)
    return {
        width: {
            address: int.from_bytes(data[offset:offset + width], "little")
            for offset in range(0, length - width + 1, width)
            for address in [start + offset]
        }
        for width in (1, 2, 4)
    }


def print_changes(previous, current):
    found = False
    for width in (4, 2, 1):
        for address, old_value in previous[width].items():
            new_value = current[width][address]
            if old_value != new_value:
                if not found:
                    print("Changed values:")
                    found = True
                print(
                    f"  {width * 8:2}-bit  0x{address:08X}: "
                    f"0x{old_value:0{width * 2}X} -> 0x{new_value:0{width * 2}X} "
                    f"({old_value} -> {new_value})"
                )
    if not found:
        print("No changed values in the selected window.")


def connect():
    pine = Pine()
    pine.connect()
    if not pine.is_connected():
        raise ConnectionError("Could not connect to PCSX2 PINE.")

    game_id = pine.get_game_id().strip().upper().replace("_", "-")
    if game_id != EXPECTED_GAME_ID:
        pine.disconnect()
        raise RuntimeError(f"Wrong game loaded: {game_id or 'unknown'}; expected {EXPECTED_GAME_ID}.")
    return pine


def interactive(pine, start, length, interval):
    print("Burnout 3 Crash Mode memory probe (read-only)")
    print(f"CrashScore window: 0x{start:08X}..0x{start + length - 1:08X}")
    print("Commands: dump, mark, diff, watch [seconds], help, quit")
    baseline = None

    while True:
        try:
            command = input("probe> ").strip().split()
        except EOFError:
            return
        if not command:
            continue
        if command[0] in {"quit", "exit"}:
            return
        if command[0] == "help":
            print("dump: print named Crash Mode values")
            print("mark: save the current memory window as a baseline")
            print("diff: compare current memory with the baseline")
            print("watch [seconds]: print named values when they change")
            continue
        if command[0] == "dump":
            print_fields(read_fields(pine))
            continue
        if command[0] == "mark":
            baseline = read_window(pine, start, length)
            print("Baseline saved.")
            continue
        if command[0] == "diff":
            if baseline is None:
                print("No baseline. Use 'mark' first.")
                continue
            print_changes(baseline, read_window(pine, start, length))
            continue
        if command[0] == "watch":
            seconds = float(command[1]) if len(command) > 1 else 10.0
            previous = read_fields(pine)
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                time.sleep(interval)
                current = read_fields(pine)
                changes = [name for name in current if current[name] != previous[name]]
                if changes:
                    print(f"Changed: {', '.join(changes)}")
                    print_fields(current)
                previous = current
            continue
        print("Unknown command. Use 'help'.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=lambda value: int(value, 0), default=CRASH_SCORE_BASE)
    parser.add_argument("--length", type=lambda value: int(value, 0), default=0x1900)
    parser.add_argument("--interval", type=float, default=0.1)
    args = parser.parse_args()

    pine = None
    try:
        pine = connect()
        interactive(pine, args.start, args.length, args.interval)
    except (ConnectionError, RuntimeError, ValueError) as error:
        parser.error(str(error))
    finally:
        if pine is not None:
            pine.disconnect()


if __name__ == "__main__":
    main()