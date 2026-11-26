# Guion de presentación: la historia de doña Rosa

Duración: 7 minutos más preguntas. Jurado: un gerente de banca, un gerente de telecomunicaciones y un médico. Regla de oro: cada vez que aparezca un término técnico, va acompañado de una comparación que ellos ya conocen.

Prepara antes de entrar:
- Backend corriendo y un análisis ya hecho con los datasets completos **más** el archivo de citas `agendamiento_sintetico.csv` (unos 3 minutos).
- Una pestaña en el portal de denuncias (`/denuncia`) y otra en el ingreso (`/ingresar`).
- Para la parte en vivo se procesan los datos de `datos_ejemplo`, que tardan unos 10 segundos.

## 1. Apertura (40 s)

> Doña Rosa tiene 68 años y es jubilada. Necesita una cita con el cardiólogo. Un lunes a las 7:00, cuando se abre la agenda, entra al chatbot de la página: no hay turnos. Diez minutos después le llega un WhatsApp: "Le consigo la cita para mañana, son 20 dólares".
>
> Esa misma semana, un sábado, una cuenta que nadie había usado en todo el mes entra al sistema médico, descarga información y desaparece.
>
> Doña Rosa nunca se va a enterar de lo segundo. Y lo primero le parece normal, porque "así funciona".

Pausa. Luego:

> Nosotros revisamos lo que pasó en octubre. Y ninguna de las dos cosas es normal.

## 2. El problema en una cifra (30 s)

> En un mes, el firewall y el sistema médico generan **10 millones de registros**. Una persona leyendo uno por segundo, ocho horas al día, necesitaría **348 jornadas**: más de un año de trabajo para revisar un solo mes. Nadie lo hace. Por eso los ataques pasan.

## 3. Qué es Sentinel Salud (30 s)

Una frase para cada miembro del jurado:

- Para el médico: "Es el monitor de signos vitales de la seguridad. Vigila los registros y suena cuando algo sale del rango normal, como en terapia intensiva."
- Para la banca: "Hace con los accesos al sistema médico lo que su área de fraudes hace con las tarjetas: aprende lo normal y señala lo raro."
- Para telecomunicaciones: "Es un centro de operaciones de seguridad que cabe en un computador y corre sin internet."

## 4. Demostración siguiendo a doña Rosa (4 min)

| Paso | Pantalla | Qué decir |
|---|---|---|
| 1 | Portal de denuncias (`/denuncia`) | "Doña Rosa denuncia el WhatsApp desde el celular. No le pedimos cédula ni nombre: elige qué pasó, pone el número y recibe un código para dar seguimiento." Enviar una denuncia con el contacto `SIM-TRAMITE-02` y mostrar el código. |
| 2 | Ingreso | "Cada persona ve solo lo que necesita." Tocar la tarjeta de **Personal de salud**: todo cerrado menos verificar enlaces. Luego entrar como **Analista del SOC** y dejar que se vea el pase de acceso. |
| 3 | Cargar datos | Procesar los datos de ejemplo. "Aquí se ve el trabajo: se leen los archivos, se limpian, se cruzan las dos fuentes y, antes de mostrar nada, los nombres se convierten en seudónimos." Al terminar, en **Análisis anteriores** pulsar **Mostrar este** en el análisis de los datasets completos, para seguir con los 10 millones de registros. |
| 4 | Vista ejecutiva | Señalar el **pulso del mes**. "Esto es octubre. La línea verde es la actividad normal; cada espiga es un incidente. Cuatro incidentes, dos críticos." Leer la alerta roja: "La información sí salió. Esto obliga a evaluar la notificación que pide la Ley de Protección de Datos." |
| 5 | Citas del chatbot | Abrir el origen con la etiqueta **denuncia**. "Este origen reservó citas para 40 pacientes distintos y usa el mismo número que denunció doña Rosa. El sistema no cancela nada: recomienda llamar a cada afiliado por su contacto verificado. Así no castigamos a la hija que saca la cita de su mamá." Mostrar que los cuidadores autorizados aparecen como **Explicado**. |
| 6 | Caso C4, cuenta fantasma | Para el médico: "Se lee como un examen de laboratorio: la franja verde es el rango normal y la marca roja es este caso." Mostrar el aviso de Telegram y la decisión del analista. |
| 7 | Matriz de riesgos | Abrir la matriz y mirar dónde está R4. Ir al caso C1, descartarlo con el motivo "Prueba de carga autorizada por TI" y volver a la matriz: R4 se desliza hacia la izquierda (menos probable) y aparece el aviso de cambio. "La matriz no es un dibujo fijo: cambia con los datos y con las decisiones de las personas." |
| 8 | Accesos y bitácora (entrar como Jefatura) | "Si alguien necesita ver el nombre real detrás de un seudónimo, tiene que escribir el motivo. Queda aquí, con su nombre y la hora." Mostrar también un **Acceso denegado**. |

Si algo falla en vivo, ya hay un análisis cargado: seguir con las pantallas y no esperar.

## 5. Por qué le conviene a la institución (45 s)

- **Tiempo**: lo que a una persona le tomaría más de un año, el motor lo hace en unos 3 minutos con los 10 millones de registros del reto. Encontró los cuatro ataques.
- **Cumplimiento**: seudónimos en todas las pantallas, reidentificación solo con motivo y una alerta cuando la información salió, que es lo que pide la Ley Orgánica de Protección de Datos Personales.
- **Confianza de los afiliados**: un canal donde denunciar sin miedo y con respuesta. Cada denuncia se cruza con las citas.
- **Costo**: software libre, corre en un equipo local, sin licencias ni nube. El costo real es el tiempo del analista, que ahora se dedica a decidir y no a buscar.
- **Se puede llevar a otros sectores**: el mismo esquema sirve para fraude en banca o para cambio de SIM en telecomunicaciones.

## 6. Cierre (20 s)

> Volvamos a doña Rosa. Esta semana la llaman del número oficial para confirmar su cita, y ella dice "esa cita no la pedí yo". El turno vuelve a la lista de espera. La cuenta fantasma ya está suspendida, y alguien en el SOC recibió el aviso en su teléfono el mismo día.
>
> Sentinel Salud no reemplaza a las personas. Les devuelve el tiempo para decidir.

## Preguntas probables

| Pregunta | Respuesta corta |
|---|---|
| ¿Y si el sistema se equivoca? | Nada es automático: el sistema recomienda y una persona decide. Los cuidadores y operadores autorizados se reconocen y no se marcan. Si se descarta un caso, la matriz se corrige sola. |
| ¿Funciona con datos reales? | Con los datasets del reto: 10 millones de filas en unos 3 minutos y los 4 ataques encontrados. El módulo de citas se probó con datos sintéticos; es una prueba preliminar y lo decimos así. |
| ¿Cuánto cuesta? | Usa software libre y corre en un computador. No hay licencias ni servicios en la nube. |
| ¿Qué pasa con la privacidad de los pacientes? | Las pantallas solo muestran seudónimos. El nombre real está en una tabla aparte que no sale del equipo y que solo se consulta con un motivo registrado. |
| ¿Por qué no bloquear directamente al tramitador? | Porque muchas veces detrás hay un familiar o un cuidador. Primero se confirma con el afiliado; si él desconoce la cita, el turno vuelve a la lista de espera. |
| ¿Qué es Isolation Forest? | Un modelo que mide qué tan fácil es separar a un usuario del resto. Lo que se separa rápido es raro y merece una mirada, como un valor fuera de rango en un examen. |
| ¿Por qué Telegram? | Es gratuito, llega al teléfono del equipo de guardia y el mensaje no lleva datos personales. |

## Qué no decir

- No mostrar ni nombrar logos o textos de la institución. Decir "la institución" o "el sistema médico".
- No decir que el sistema "bloquea" o "detiene" ataques: detecta, prioriza y recomienda.
- No presentar los resultados del chatbot de citas como eficacia probada: son datos sintéticos.
