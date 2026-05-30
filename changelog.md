# Registro de cambios

## 30-05-2026

### Añadido

- Se ha añadido un sistema de moneda compartida para las apuestas en todos los comandos de juego.
- Añadido el comando `/balance` para mostrar la moneda actual de un usuario.
- Añadido el comando `/daily` para reclamar una recompensa diaria.
- Añadido el comando `/bet` para apuestas sencillas de ganar/perder con dinero en juego.
- Añadido el comando `/leaderboard` para mostrar los saldos más altos.
- Añadido el comando `/blackjack` para un blackjack interactivo y rápido.
- Añadido el comando `/poker` para un enfrentamiento rápido de póker de 5 cartas contra el crupier.
- Añadido el comando `/balatro`: un juego de tipo "arriesga tu suerte" infinito con multiplicadores crecientes.
- Añadido el comando `/roulette` con apuestas por color y paridad (rojo, negro, par, impar, verde).
- Añadidos los comandos `/votebet create` y `/votebet status` para apuestas de predicción.
- Las apuestas de predicción ahora crean encuestas reales en Discord usando reacciones (`✅` / `❌`).
- La resolución de predicciones ahora lee el resultado de la encuesta y liquida las apuestas automáticamente.
- Añadido soporte para un canal de ganadores diarios y un anuncio diario del jugador con mayor saldo.
- Añadido el comando administrativo `/settings winners_channel` para configurar el canal de anuncios de ganadores diarios.

### Actualizado

- Se actualizó el embed de ayuda en `main.py` para incluir los nuevos comandos de apuestas.
- Se actualizó `cogs/settings.py` con la nueva configuración del canal de ganadores.
- Se actualizó `/roulette` para que los resultados afecten al saldo compartido y al sistema de advertencias.
- Se actualizó la lógica de predicciones para almacenar `channel_id` y `message_id` de la encuesta.
- Se actualizó el embed de la encuesta de predicciones para incluir al creador y la fecha exacta de resolución.

### Notas

- El nuevo sistema de apuestas usa `gambling_data.json` para almacenar los saldos de usuarios, advertencias, reclamos diarios y el estado de predicciones.
- Todos los archivos modificados han sido validados sintácticamente con comprobaciones de Python.

---

## Mensaje para Discord (listo para pegar)

**Actualización (30/05/2026) — Nuevas funciones de apuestas 🎲**

Se han añadido y actualizado varios comandos y el sistema de economía compartida:

**Novedades**
- 💰 Sistema de moneda compartida para apuestas.
- `/balance` — Mostrar saldo.
- `/daily` — Reclamar recompensa diaria.
- `/bet` — Apuesta simple (ganar/perder).
- `/leaderboard` — Top de saldos.
- `/blackjack` — Blackjack interactivo rápido.
- `/poker` — Póker de 5 cartas contra el crupier.
- `/balatro` — Juego “arriesga tu suerte” con multiplicadores.
- `/roulette` — Apuestas por color/paridad (rojo, negro, par, impar, verde).
- `/votebet create` y `/votebet status` — Apuestas de predicción con encuestas (`✅` / `❌`).
- Las predicciones se resuelven leyendo los votos y se liquidan automáticamente.
- Soporte para anunciar ganadores diarios y el jugador con mayor saldo.
- `/settings winners_channel` — Comando admin para configurar el canal de anuncios.

**Notas**
- Los datos se almacenan en `gambling_data.json`.
- Todos los cambios han pasado comprobaciones sintácticas de Python.

Pega este bloque tal cual en el canal de novedades para informar al servidor.
