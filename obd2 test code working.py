import obd

connection = obd.OBD(fast=False)

if not connection.is_connected():
    print("No OBD-II connection.")
    exit()

CMD_IAT = obd.commands.INTAKE_TEMP
ELM_VOLT = obd.commands.ELM_VOLTAGE

iat = connection.query(CMD_IAT)
volt = connection.query(ELM_VOLT)

# Safe checks
if not iat.is_null():
    print("Intake Air Temp:", iat.value)
else:
    print("Intake Air Temp: N/A")

if not volt.is_null():
    print("ELM Voltage:", volt.value)
else:
    print("ELM Voltage: N/A")
