#!/usr/bin/python3

import unittest
import geet

@geet.subcommand()
def testing(args):
    """testing: testing the cli api

    Aliases: t, test

    Args:
       branch: branch to integrate
       files...: One or more files.
       -k|--kill: kill
    """
    print(f"{args!r}")

@geet.subcommand()
def foobar(args):
    """foobar: foo the bars

    foo foo bar bar
    """
    pass

class GeetCliTest(unittest.TestCase):

    def test_upper(self):
        self.assertEqual('foo'.upper(), 'FOO')

    def test_isupper(self):
        self.assertTrue('FOO'.isupper())
        self.assertFalse('Foo'.isupper())

    def test_split(self):
        s = 'hello world'
        self.assertEqual(s.split(), ['hello', 'world'])
        # check that s.split fails when the separator is not a string
        with self.assertRaises(TypeError):
            s.split(2)

if __name__ == '__main__':
    unittest.main()
