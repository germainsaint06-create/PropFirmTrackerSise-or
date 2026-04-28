# Prop Firm Tracker

Sistema de control de cuentas, reglas y trades para multiples prop firms.

## Que hace

- Gestiona cuentas en multiples prop firms (Trading Pit, For Traders, FTMO, etc.)
- Vigila reglas especificas por firma: limites de lotaje, riesgo USD, dias de inactividad
- Registra cada trade y detecta automaticamente violaciones de reglas
- Dashboard con alertas tempranas (verde / amarillo / rojo / breach)
- Trackea spread por activo en cada operacion

## Estructura

```
tracker/
  app.py                  <- entrada principal
  db.py                   <- base de datos SQLite
  rules_engine.py         <- motor de alertas y validaciones
  seed.py                 <- carga inicial de firms y reglas
  pages/
    1_Dashboard.py        <- vista detallada de cuentas
    2_Cuentas.py          <- alta/edicion/archivo de cuentas
    3_Trades.py           <- registro y listado de trades
    4_Reglas.py           <- vista y edicion de reglas
  data/
    tracker.db            <- archivo de base de datos (se crea automaticamente)
  requirements.txt
  .streamlit/
    config.toml           <- tema oscuro
```

## Como correrlo localmente

1. Instala Python 3.10 o superior.

2. En una terminal, dentro de la carpeta `tracker/`:
   ```bash
   pip install -r requirements.txt
   python seed.py
   streamlit run app.py
   ```

3. Se abre el navegador automaticamente. Contrasena por defecto: `admin`
   (cambiala antes de desplegar)

## Como desplegarlo en Streamlit Community Cloud (gratis)

1. Crea cuenta en https://github.com (si no tienes).
2. Crea un repo nuevo (privado) y sube esta carpeta entera.
3. Ve a https://share.streamlit.io y conecta tu GitHub.
4. New app -> selecciona el repo -> archivo principal: `app.py`.
5. En "Advanced settings -> Secrets", agrega:
   ```
   APP_PASSWORD = "tu-contrasena-secreta-aqui"
   ```
6. Deploy. Te da una URL publica accesible desde cualquier navegador.

Importante: el archivo `data/tracker.db` se persiste entre reinicios en
Streamlit Community Cloud, pero como buena practica haz backup periodico
descargando el archivo desde la pagina (lo agregamos en Fase 2).

## Backup

El archivo `data/tracker.db` ES tu base de datos completa. Cada cierto
tiempo, copialo a otra ubicacion (Google Drive, Dropbox, etc.).
Si pierdes ese archivo, pierdes los datos.
