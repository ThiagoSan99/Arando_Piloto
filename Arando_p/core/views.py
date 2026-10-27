from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(['GET'])
def estado_api(request):
    return Response({
        "sistema": "Arando la Educación",
        "modulo": "API Backend",
        "estado": "operativo"
    })