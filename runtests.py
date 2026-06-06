import sys
import pytest


def main() -> int:
    args = [
        'tests',
        '-v',
    ]
    return pytest.main(args)


if __name__ == '__main__':
    sys.exit(main())
