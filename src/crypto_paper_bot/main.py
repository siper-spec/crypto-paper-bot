from .runner import run_once

def main() -> None:
    run_once(send_alerts=False)

if __name__ == '__main__':
    main()
