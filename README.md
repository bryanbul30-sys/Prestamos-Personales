# Control de Prestamos

App web (Streamlit) para llevar el control de tus prestamos personales,
usando Google Sheets como base de datos.

Hoja de Google ya creada: https://docs.google.com/spreadsheets/d/1glEZrmTJZIBUexzPuEMUdxjxAMEKsisdO8EXPuNc64U/edit

## Como funciona el interes

Cada prestamo tiene su propia tasa de interes por periodo. Cada vez que
registras un pago, la app calcula el interes sobre el saldo pendiente de
ese prestamo (saldo x tasa). Si el pago es mayor al interes, la diferencia
abona a capital. Si el pago es menor o igual, no se abona capital ese
periodo (el interes no cubierto no se acumula ni genera interes sobre
interes).

## Paso 1 - Crear la cuenta de servicio de Google

1. Entra a https://console.cloud.google.com/ con tu cuenta bryan.bul30@gmail.com.
2. Crea un proyecto nuevo, por ejemplo "control-prestamos".
3. Ve a "APIs y servicios" > "Biblioteca" y activa:
   - Google Sheets API
   - Google Drive API
4. Ve a "APIs y servicios" > "Credenciales" > "Crear credenciales" >
   "Cuenta de servicio". Dale cualquier nombre (ej. "prestamos-app").
5. Entra a la cuenta de servicio creada > pestana "Claves" > "Agregar
   clave" > "Crear clave nueva" > tipo JSON. Se descarga un archivo.
6. Renombra ese archivo a `credenciales.json` y ponlo dentro de esta
   carpeta (`C:\prestamos-tracker`). Nunca lo compartas ni lo subas a
   ningun repositorio publico (ya esta en `.gitignore`).
7. Abre `credenciales.json`, copia el valor de `"client_email"`
   (algo como `prestamos-app@control-prestamos-123456.iam.gserviceaccount.com`).

## Paso 2 - Compartir la Hoja de Google con la cuenta de servicio

1. Abre la hoja: https://docs.google.com/spreadsheets/d/1glEZrmTJZIBUexzPuEMUdxjxAMEKsisdO8EXPuNc64U/edit
2. Boton "Compartir" > pega el `client_email` del paso anterior > dale
   rol **Editor** > Enviar.

## Paso 3 - Instalar dependencias

```bash
pip install -r requirements.txt
```

## Paso 4 - Construir la estructura de la hoja (una sola vez)

```bash
python setup_sheet.py
```

Esto crea las pestanas Prestamos, Pagos y Resumen con formulas,
formato y validacion de datos. Es seguro volver a correrlo despues;
no borra los prestamos/pagos que ya hayas cargado.

## Paso 5 - Correr la app

```bash
streamlit run app.py
```

Se abre en el navegador. Tiene tres pestanas:

- **Resumen**: totales del negocio y lista de prestamos atrasados.
- **Prestamos**: tabla de todos los prestamos + formulario para
  registrar uno nuevo.
- **Registrar pago**: formulario para anotar un pago recibido +
  historial de pagos.

## Estructura del proyecto

```
config.py          ID de la hoja y ruta de credenciales
sheets_client.py    conexion compartida a Google Sheets
setup_sheet.py       construye la estructura de la hoja (correr una vez)
app.py               la app web (Streamlit)
requirements.txt
Control de Prestamos.xlsx   plantilla de respaldo en Excel (mismo diseno)
```

## Pendiente / posibles siguientes pasos

- Migrar los prestamos historicos de tu archivo original
  `Control de Pan1.xlsx` (pestana "Prestamos", 171 filas) a este nuevo
  formato -- no se hizo automatico porque los codigos de frecuencia y
  tasas de ese archivo son inconsistentes; conviene revisarlo prestamo
  por prestamo.
- Acceso para clientes (que cada quien vea su propio saldo) -- quedo
  pendiente de decidir si vale la pena.
- Recordatorios proactivos (WhatsApp/email/Telegram) en vez de solo
  el resaltado visual de "Atrasado" dentro de la app.
