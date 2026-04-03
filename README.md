# Calculador de Probables Quinela

Herramienta manual, ligera e independiente para consultar probables **reales** de la apuesta **Quinela** desde Teletrak.

Este proyecto es 100% paralelo al predictor principal y no se integra con ninguna otra herramienta de pronóstico.

## Qué hace

- Permite elegir hipódromo, fecha y número de carrera.
- Recibe 6 números de caballo ingresados manualmente.
- Resuelve el `race_id` real de Teletrak para esa carrera.
- Consulta la matriz real de probables Quinela disponible en Teletrak.
- Filtra únicamente las 15 combinaciones de la Quinela Box.
- Muestra un resumen rápido y una tabla clara con los dividendos actuales.

## Qué no hace

- No usa fallback simulado.
- No inventa dividendos.
- No usa base de datos.
- No guarda historial.
- No depende de ClaudePredictor, Antigravity, starless-predictor ni del proyecto principal.

Si Teletrak no tiene la matriz Quinela publicada para esa carrera, la app muestra solo este mensaje:

`Probables Quinela aún no disponibles en Teletrak`

## Estructura del proyecto

```text
CalculadorApuestas/
├─ app.py
├─ live_odds.py
├─ requirements.txt
├─ README.md
└─ .gitignore
```

## Requisitos

- Python 3.11 o superior recomendado
- Acceso a internet para consultar Teletrak

## Ejecutar localmente en Windows

```powershell
cd "C:\Users\edudi\Desktop\CalculadorApuestas"
py -m pip install -r requirements.txt
py -m streamlit run app.py
```

## Uso

1. Elegir hipódromo.
2. Elegir fecha.
3. Ingresar número de carrera.
4. Ingresar 6 números de caballo distintos.
5. Presionar `Consultar Probables`.

## Despliegue en Streamlit Community Cloud

1. Sube este proyecto a un repositorio propio de GitHub.
2. Entra a [Streamlit Community Cloud](https://share.streamlit.io/).
3. Crea una nueva app conectando ese repositorio.
4. Selecciona la rama principal del repositorio.
5. Define `app.py` como archivo principal.
6. Despliega la aplicación.

## Notas para Streamlit Cloud

- El entrypoint correcto es `app.py`.
- No hay rutas locales fijas.
- No se requieren variables de entorno ni secretos para el MVP.
- La app solo muestra dividendos cuando Teletrak entrega datos reales.

## Licencia

Uso privado o personal, salvo que decidas publicar otra licencia en GitHub.
