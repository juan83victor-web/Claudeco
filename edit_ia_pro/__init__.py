"""EDIT IA PRO: edição automática de vídeos curtos verticais (Reels, anúncios).

Implementa o roteiro "EDIT IA PRO · Modo celular": cortar pausas e tomadas
repetidas, legendas animadas, gancho escrito, zoom nos cortes, animações 2D
nos momentos fortes, efeitos sonoros, trilha, volume final e conferência de
frases que a Meta reprova.
"""

__version__ = "0.1.0"

LARGURA = 1080
ALTURA = 1920
FPS = 30

# Zona segura do Reels: todo texto precisa ficar aqui dentro.
ZONA_SEGURA = (140, 230, 940, 1530)  # x0, y0, x1, y1
