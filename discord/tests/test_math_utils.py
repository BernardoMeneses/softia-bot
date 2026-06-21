import unittest

from bot import math_utils


class MathUtilsTest(unittest.TestCase):
    def test_binary_operations(self):
        self.assertEqual(math_utils.add(2, 3), 5)
        self.assertEqual(math_utils.subtract(8, 3), 5)
        self.assertEqual(math_utils.multiply(4, 3), 12)
        self.assertEqual(math_utils.divide(8, 2), 4)
        self.assertEqual(math_utils.modulo(10, 3), 1)
        self.assertEqual(math_utils.power(2, 3), 8)

    def test_divide_by_zero_raises(self):
        with self.assertRaises(math_utils.MathCommandError):
            math_utils.divide(1, 0)

    def test_square_and_cube_roots(self):
        self.assertEqual(math_utils.nth_root(9), 3)
        self.assertEqual(math_utils.nth_root(27, 3), 3)
        self.assertEqual(math_utils.nth_root(-27, 3), -3)

    def test_even_root_of_negative_raises(self):
        with self.assertRaises(math_utils.MathCommandError):
            math_utils.nth_root(-4, 2)

    def test_matrix_multiply(self):
        left, right = math_utils.parse_matrix_expression("[[1,2],[3,4]] * [[5,6],[7,8]]")
        self.assertEqual(math_utils.matrix_multiply(left, right), [[19, 22], [43, 50]])

    def test_invalid_matrix_dimensions_raise(self):
        left, right = math_utils.parse_matrix_expression("[[1,2,3]] * [[1,2]]")
        with self.assertRaises(math_utils.MathCommandError):
            math_utils.matrix_multiply(left, right)


if __name__ == "__main__":
    unittest.main()
