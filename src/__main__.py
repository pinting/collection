import sys

from src.config import STAGES, Config, parse_args
from src.stages.movies import MoviesStage
from src.stages.music import MusicStage


def create_stage(name: str, config: Config):
    match name:
        case "music":
            return MusicStage(config)
        case "movies":
            return MoviesStage(config)
        case _:
            raise ValueError(f"Unknown stage: {name}")


def main() -> None:
    config = parse_args()
    names = [name for name in STAGES if name in config.stages]

    print(f"Stages: {', '.join(names)}")
    print(f"Workers: {config.workers}")
    print(f"Limit: {config.limit or 'none'}")
    if "music" in names:
        print(f"Music Dir: {config.music_dir or '(not set)'}")
        print(f"Export Music CSV: {config.export_music_csv}")
    if "movies" in names:
        print(f"Movies Source: {config.movies_txt or config.movies_dir or '(not set)'}")
        print(f"Export Movies CSV: {config.export_movies_csv}")
    print()

    try:
        for name in names:
            stage = create_stage(name, config)
            stage.run()
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(130)

    print("\nDone.")


if __name__ == "__main__":
    main()
