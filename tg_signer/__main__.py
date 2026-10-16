import sys


def signer():
    if sys.argv[1:] == ["version"]:
        from tg_signer import __version__

        print(f"tg-signer {__version__}")
        return
    from tg_signer import cli

    sys.exit(cli.tg_signer())


if __name__ == "__main__":
    signer()
