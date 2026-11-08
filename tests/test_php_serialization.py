import unittest
from decimal import Decimal

from app.php_serialization import dumps, loads


class PhpSerializationTests(unittest.TestCase):
    def test_scalar_array_and_utf8_byte_lengths(self):
        self.assertEqual(dumps({'title': 'Бумага', 'cost': Decimal('12.50')}),
                         'a:2:{s:5:"title";s:12:"Бумага";s:4:"cost";d:12.50;}')
        self.assertEqual(dumps([True, None, 3]), 'a:3:{i:0;b:1;i:1;N;i:2;i:3;}')

    def test_non_finite_values_are_rejected(self):
        with self.assertRaises(ValueError):
            dumps(Decimal('NaN'))

    def test_safe_roundtrip_with_russian_text_and_nested_arrays(self):
        value = {'title':'Бумага', 'blanks':{2:{'price':Decimal('12.50'), 'active':True}}, 'empty':None}
        self.assertEqual(loads(dumps(value)),value)

    def test_objects_references_truncated_and_oversized_arrays_rejected(self):
        for value in ('O:3:"Foo":0:{}', 'R:1;', 'a:1:{i:0;}', 's:10:"short";', 'a:999999:{}', 'i:1;trailing'):
            with self.subTest(value=value), self.assertRaises((ValueError, UnicodeError)):
                loads(value)