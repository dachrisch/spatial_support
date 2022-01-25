import json
import os
from base64 import urlsafe_b64encode
from logging import basicConfig, INFO, DEBUG
from logging import getLogger
from pathlib import Path

from space import SpaceFactory


class SpaceProcessor:
    def __init__(self, space_name, space_password):
        self.space = SpaceFactory.connect(space_name, space_password)
        self.debug = getLogger(self.__class__.__name__).debug
        self.info = getLogger(self.__class__.__name__).info

    def hibernate(self, directory, user='hibernate'):
        joined_space = self.space.join(user)
        hibernate_path = Path(directory).joinpath(joined_space.space.name).expanduser()
        hibernate_path.mkdir(parents=True, exist_ok=True)
        joined_space.hibernate(hibernate_path)


    def restore(self, directory, user='restore'):
        restore_path = Path(directory).expanduser()
        joined_space = self.space.join(user)
        joined_space.resume(restore_path)




def main():
    basicConfig(level=DEBUG)

    sp = SpaceProcessor(os.getenv('space_name'), os.getenv('space_password'))
    # sp.hibernate('~/Downloads/spatial_test')

    sp.restore('~/Downloads/spatial_test/test')


if __name__ == '__main__':
    main()
