# Claude Limits

Widget de escritorio para Windows que muestra, siempre a la vista, cuánto
llevas gastado de tus límites de Claude: la sesión de 5 horas en una barra
y, al pasar el ratón, el límite semanal y el de cada modelo, con una
previsión de si llegarás al reinicio.

## Descargar e instalar

1. Ve a [**Releases**](../../releases/latest) y descarga
   `Claude-Limits-1.0.zip`.
2. Descomprímelo entero en una carpeta.
3. Doble clic en `INSTALAR.bat`.
4. Pulsa **Abrir ventana** e inicia sesión en Claude como siempre: la ventana
   se cierra sola y el widget queda conectado.

Si Windows avisa con "Windows protegió tu PC": *Más información* ›
*Ejecutar de todas formas* (el programa no está firmado digitalmente).

Las instrucciones completas están en `LEEME - Instrucciones.txt`, dentro del
zip.

## Qué hace

- Barra con el porcentaje de la sesión de 5 h y la cuenta atrás
  Si tu plan no tiene límite de 5 h (algunos de empresa), la barra
  muestra el semanal.
- Panel al pasar el ratón: límite semanal y por modelo, con previsión.
- Punto de aviso en la barra si algún límite semanal está agotado.
- Varias cuentas de Claude y cambio entre ellas desde el menú.
- Inicio de sesión desde el propio widget, en tu navegador.
- La clave de acceso se guarda en el Administrador de credenciales de
  Windows, nunca en un archivo.
- Tema claro u oscuro, colores (también uno propio) y tamaño.
- Avisa cuando hay versión nueva y se actualiza con un clic.

## Privacidad

El widget solo habla con `claude.ai` (para leer tu consumo) y con GitHub
(para saber si hay versión nueva). No envía datos a ningún otro sitio.

## Compilar desde el código

Hace falta Python 3 con `pillow` y `pyinstaller`. `COMPILAR.bat` genera
`Claude Limits.exe`; `COMPILAR PRUEBA.bat` genera una copia de prueba que
convive con la instalada.
