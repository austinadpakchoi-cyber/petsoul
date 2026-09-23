"""Run the local read-only coordination board: python -B scripts/serve_blackboard.py."""
import argparse
from pathlib import Path

from coordination_board.server import BoardServer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--port", type=int, default=18770)
    args = parser.parse_args()
    with BoardServer(args.repo, args.port) as server:
        print(f"PetSoul blackboard: http://127.0.0.1:{server.server_port}", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
