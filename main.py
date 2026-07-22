import argparse


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="YuGong — automated wiki editing tool"
    )
    parser.add_argument(
        '--dev', nargs=2, metavar=('INPUT', 'OUTPUT'),
        help='Run extensions locally: read wikitext from INPUT file, '
             'write processed result to OUTPUT file (no wiki connection)'
    )

    args = parser.parse_args()

    if args.dev:
        from src.Yugong.processor.dev_mode import run_dev_mode
        input_path, output_path = args.dev
        run_dev_mode(input_path, output_path)
    else:
        from src.Yugong.yu_gong import yu_gong
        yu_gong()
