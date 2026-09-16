"""
Validadores de contraseña propios del proyecto.

Django trae varios de fábrica (longitud mínima, contraseñas comunes, contraseñas
solo numéricas). Aquí se agrega el que exige la especificación: que la contraseña
combine letras y números (RF-SEG-01).
"""

from django.core.exceptions import ValidationError


class LetrasYNumerosValidator:
    """Rechaza contraseñas que no tengan al menos una letra y un número."""

    def validate(self, password, user=None):
        tiene_letra = any(caracter.isalpha() for caracter in password)
        tiene_numero = any(caracter.isdigit() for caracter in password)

        if not (tiene_letra and tiene_numero):
            raise ValidationError(
                "La contraseña debe combinar letras y números.",
                code="contrasena_sin_letras_o_numeros",
            )

    def get_help_text(self):
        return "La contraseña debe tener al menos una letra y un número."
