import unittest
import xmlrunner
import os

PARENT_FOLDER = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = PARENT_FOLDER

import uio


class MyTest(unittest.TestCase):
    def test_dummy(self):
        assert True

    def test_file_exists(self):
        assert uio.file_exists("slalom/__init__.py")


if __name__ == "__main__":
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output="test-reports"))
    # x = MyTest()
    # x.test_safe_writes()
