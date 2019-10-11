import unittest
import xmlrunner
import os
import re

PARENT_FOLDER = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = PARENT_FOLDER

from slalom.dataops import io

class MyTest(unittest.TestCase):
    def test_dummy(self):
        assert True

    def test_file_exists(self):
        assert io.file_exists("slalom/__init__.py")


if __name__ == '__main__':
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'))
    # x = MyTest()
    # x.test_safe_writes()
