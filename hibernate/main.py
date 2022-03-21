import os
from argparse import ArgumentParser
from logging import basicConfig, INFO
from logging import getLogger
from pathlib import Path

from space import SpaceFactory


class SpaceProcessor:
    def __init__(self, space_name, space_password):
        self.space = SpaceFactory.connect(space_name, space_password)
        self.debug = getLogger(self.__class__.__name__).debug
        self.info = getLogger(self.__class__.__name__).info

    def hibernate(self, directory, user='hibernate'):
        joined_space = self.space.connect(account.secret)
        hibernate_path = Path(directory).joinpath(joined_space.space.name).expanduser()
        hibernate_path.mkdir(parents=True, exist_ok=True)
        joined_space.hibernate(hibernate_path)

    def restore(self, directory, user='restore'):
        restore_path = Path(directory).expanduser()
        joined_space = self.space.connect(account.secret)
        joined_space.resume(restore_path)


def main():
    basicConfig(level=INFO)
    parser = ArgumentParser()

    parser.add_argument('space', help='space name to work on')
    parser.add_argument('password', help='space admin password')
    parser.add_argument('directory', help='directory to store/restore content', default=Path(os.getcwd()))
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-s", "--store", help="hibernate a given space", action="store_true")
    group.add_argument("-r", "--restore", help="resume a given space", action="store_true")

    args = parser.parse_args()
    sp = SpaceProcessor(args.space, args.password)

    if args.store:
        sp.hibernate(args.directory)
    elif args.restore:
        sp.restore(args.directory)


if __name__ == '__main__':
    main()
