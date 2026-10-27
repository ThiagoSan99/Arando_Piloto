
import os
import requests


class KoboClient:
    BASE_URL = "https://kf.kobotoolbox.org/api/v2"

    FORM_UID = os.getenv(
        "KOBO_FORM_UID",
        "aS3JhBzNuufeAQMPAQN3jX"
    )

    def __init__(self):
        self.token = os.environ.get("KOBO_API_TOKEN")

        if not self.token:
            raise ValueError(
                "No se ha configurado KOBO_API_TOKEN"
            )

        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Token {self.token}",
            "Accept": "application/json"
        })

    def obtener_formulario(self):
        """
        Consulta la información del formulario
        de asistencias de Arando la Educación.
        """

        url = (
            f"{self.BASE_URL}/assets/"
            f"{self.FORM_UID}/"
        )

        respuesta = self.session.get(
            url,
            timeout=30
        )

        respuesta.raise_for_status()

        return respuesta.json()

    def obtener_respuestas(self, limite=10):
        """
        Consulta las respuestas del formulario
        de asistencias desde KoboToolbox.

        No modifica ni almacena los registros.
        """

        url = (
            f"{self.BASE_URL}/assets/"
            f"{self.FORM_UID}/data/"
        )

        respuesta = self.session.get(
            url,
            params={"limit": limite},
            timeout=30
        )

        respuesta.raise_for_status()

        return respuesta.json()


    def iterar_respuestas(self, tamano_pagina=100):
        """
        Recorre las respuestas de KoboToolbox página por página.
        No carga todas las respuestas en memoria.
        """

        if tamano_pagina < 1:
            raise ValueError(
                "El tamaño de página debe ser mayor que cero."
            )

        from urllib.parse import urlparse

        url = (
            f"{self.BASE_URL}/assets/"
            f"{self.FORM_UID}/data/"
        )

        parametros = {"limit": tamano_pagina}

        while url:
            # Evitar enviar el token a dominios externos
            destino = urlparse(url)

            if (
                destino.scheme != "https"
                or destino.hostname != "kf.kobotoolbox.org"
                or not destino.path.startswith(
                    f"/api/v2/assets/{self.FORM_UID}/data/"
                )
            ):
                raise ValueError(
                    "KoboToolbox devolvió una URL de paginación no permitida."
                )

            respuesta = self.session.get(
                url,
                params=parametros,
                timeout=30
            )

            respuesta.raise_for_status()

            datos = respuesta.json()

            for registro in datos.get("results", []):
                yield registro

            url = datos.get("next")
            parametros = None
