from __future__ import annotations

import ast
import math
from typing import Iterable


class MathCommandError(ValueError):
    """Raised when a math command receives invalid input."""


Matrix = list[list[float]]


def parse_number(value: str) -> float:
    normalized = value.strip().replace(",", ".")
    try:
        return float(normalized)
    except ValueError as exc:
        raise MathCommandError(f"`{value}` nao e um numero valido.") from exc


def format_number(value: float) -> str:
    if not math.isfinite(value):
        return str(value)

    rounded = round(value)
    if abs(value - rounded) < 1e-10:
        return str(int(rounded))

    return f"{value:.10g}"


def add(left: float, right: float) -> float:
    return left + right


def subtract(left: float, right: float) -> float:
    return left - right


def multiply(left: float, right: float) -> float:
    return left * right


def divide(left: float, right: float) -> float:
    if right == 0:
        raise MathCommandError("Nao e possivel dividir por zero.")
    return left / right


def modulo(left: float, right: float) -> float:
    if right == 0:
        raise MathCommandError("Nao e possivel calcular modulo por zero.")
    return left % right


def power(base: float, exponent: float) -> float:
    return base**exponent


def nth_root(value: float, degree: float = 2) -> float:
    if not degree.is_integer():
        raise MathCommandError("O grau da raiz tem de ser um numero inteiro.")

    degree_as_int = int(degree)
    if degree_as_int <= 0:
        raise MathCommandError("O grau da raiz tem de ser maior que zero.")

    if value < 0:
        if degree_as_int % 2 == 0:
            raise MathCommandError("Raizes pares de numeros negativos nao sao reais.")
        return -((-value) ** (1 / degree_as_int))

    return value ** (1 / degree_as_int)


def parse_matrix_expression(expression: str) -> tuple[Matrix, Matrix]:
    if "*" not in expression:
        raise MathCommandError("Uso: `-matrix [[1,2],[3,4]] * [[5,6],[7,8]]`")

    left_raw, right_raw = expression.split("*", 1)
    return parse_matrix(left_raw), parse_matrix(right_raw)


def parse_matrix(raw: str) -> Matrix:
    try:
        value = ast.literal_eval(raw.strip())
    except (SyntaxError, ValueError) as exc:
        raise MathCommandError("Matriz invalida. Usa listas, por exemplo `[[1,2],[3,4]]`.") from exc

    if not isinstance(value, (list, tuple)) or not value:
        raise MathCommandError("A matriz tem de ser uma lista de linhas.")

    matrix: Matrix = []
    width: int | None = None

    for row in value:
        if not isinstance(row, (list, tuple)) or not row:
            raise MathCommandError("Cada linha da matriz tem de ser uma lista nao vazia.")

        parsed_row = [_coerce_matrix_number(item) for item in row]
        if width is None:
            width = len(parsed_row)
        elif len(parsed_row) != width:
            raise MathCommandError("Todas as linhas da matriz tem de ter o mesmo tamanho.")

        matrix.append(parsed_row)

    return matrix


def _coerce_matrix_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MathCommandError("As matrizes so podem conter numeros.")
    return float(value)


def matrix_multiply(left: Matrix, right: Matrix) -> Matrix:
    left_width = len(left[0])
    right_height = len(right)

    if left_width != right_height:
        raise MathCommandError(
            "Dimensoes invalidas: o numero de colunas da primeira matriz "
            "tem de ser igual ao numero de linhas da segunda."
        )

    right_width = len(right[0])
    result: Matrix = []

    for row_index in range(len(left)):
        result_row: list[float] = []
        for col_index in range(right_width):
            cell = sum(left[row_index][inner] * right[inner][col_index] for inner in range(left_width))
            result_row.append(cell)
        result.append(result_row)

    return result


def format_matrix(matrix: Iterable[Iterable[float]]) -> str:
    rows = []
    for row in matrix:
        rows.append("[" + ", ".join(format_number(value) for value in row) + "]")
    return "[" + ", ".join(rows) + "]"
