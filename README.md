# Squishies ASMR · vídeo efecto pizarra (60 s)

Vídeo vertical (1080×1920, 30 fps, 60 s) con efecto *whiteboard animation*:
una mano con rotulador va escribiendo y dibujando sobre una pizarra blanca,
y un borrador limpia la pizarra entre escenas. El tema es el fenómeno viral
de los squishies ASMR. La pista de audio es ASMR sintetizado y sincronizado
con la animación: chirridos suaves del rotulador, "squish" y "pops" cuando
los squishies se colorean, y el barrido del borrador.

Resultado: `output/squishies_asmr_pizarra.mp4`.

## Guion (8 escenas)

| Escena | Tiempo | Contenido |
| --- | --- | --- |
| 1 | 0–6 s | Título "SQUISHIES ASMR", gato squishy, "¿Por qué son tan virales?" |
| 2 | 6–14 s | Así se hace ASMR: una niña sentada a un escritorio, con las manos a la vista, hace tap-tap con las uñas sobre una piña metalizada |
| 3 | 14–21 s | ¿Qué es un squishy? Espuma de lenta recuperación, *slow rise* |
| 4 | 21–28 s | El sonido ASMR: oreja, ondas, crunch · squish · pop, cerebro |
| 5 | 28–37 s | Los más virales: Taba squishies, Mochi squishies, Squishy makeover |
| 6 | 37–45 s | La fórmula viral: vídeo vertical, sonido limpio, cámara lenta y bucles |
| 7 | 45–52 s | ¿Por qué engancha? Relaja, satisfying, imposible dejar de verlo |
| 8 | 52–60 s | Cierre: ¿Te relajó? Dale like y sígueme para más ASMR |

## Cómo se genera

```
scripts/build.sh            # vídeo final en output/
scripts/build.sh --fps 15   # borrador rápido
node scripts/render.mjs --frame 12.5 --png build/f.png   # un fotograma suelto
```

- `src/index.html`: la animación completa (SVG + JS). Es determinista: `window.render(t)`
  pinta el estado en el segundo `t`, así cada fotograma se captura con exactitud. Abierto
  en un navegador se reproduce solo (espacio pausa, flechas avanzan o retroceden).
- `scripts/render.mjs`: captura los fotogramas con Playwright/Chromium y los pasa por
  tubería a ffmpeg (H.264). También exporta la línea de tiempo (`build/timeline.json`).
- `scripts/make_audio.py`: sintetiza la pista ASMR a partir de esa línea de tiempo
  (solo numpy). `--no-pad` elimina el colchón armónico de fondo.
- `assets/fonts/`: Permanent Marker, Caveat y Patrick Hand (Google Fonts, licencia OFL).

Para cambiar el guion basta editar las escenas en `src/index.html`; las duraciones,
la posición de la mano y los efectos de sonido se recalculan solos.
