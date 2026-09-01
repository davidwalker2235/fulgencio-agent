# Fulgencio Agent

## Responsabilidades

Este repositorio es el dueño del harness del agente: herramientas, argumentos, máquina de estados,
confirmaciones, acceso a Azure SQL, publicaciones en Firebase y monitorización del robot. Los
proyectos consumidores no pueden redefinir estas capacidades mediante prompts.

La conversación se compone siempre en este orden:

1. Reglas operativas inmutables de `app/agent/prompts.py`.
2. Instrucciones conversacionales del consumidor o el perfil predeterminado del agente.
3. Reglas operativas del estado actual.

Mantén esta separación al modificar el agente. Personalidad, saludo, temas permitidos, estilo y
charla de espera pertenecen a la capa conversacional. Validaciones, herramientas, transiciones y
resultados confirmados pertenecen al harness.

## Configuración desde un consumidor

Un consumidor que quiera personalizar la conversación debe conectar a:

```text
/ws?conversation_config=1
```

y enviar como primer frame de texto, antes del audio:

```json
{
  "type": "conversation.configure",
  "instructions": "Instrucciones conversacionales del proyecto"
}
```

El límite es de 16.000 caracteres. Un mensaje vacío selecciona el perfil predeterminado. Un mensaje
mal formado o demasiado largo se rechaza. Sin `conversation_config=1`, la sesión comienza
inmediatamente con el perfil predeterminado y mantiene compatibilidad con clientes anteriores.

No registres, devuelvas al frontend ni persistas las instrucciones recibidas.

## Pruebas

Ejecuta antes de entregar cambios:

```powershell
python -m unittest discover -s tests -v
```

Comprueba que un perfil personalizado nunca sustituye las reglas inmutables ni altera la lista de
herramientas del estado.

## Sesión persistente

Una sesión puede ejecutar varias experiencias consecutivas. Tras completar un regalo o cuando el
robot vuelve a `idle` después de dibujar, la máquina vuelve a `offering_options`, limpia el número
pendiente y permite elegir otra acción. Cada nueva caricatura debe pasar de nuevo por captura y
confirmación del número.

El adaptador de Fulgencio no emite `agent_end` para `response.done`; ese evento no debe interpretarse
como el fin de la conversación. El WebSocket solo termina cuando el cliente lo cierra.
