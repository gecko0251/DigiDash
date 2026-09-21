import obd

connection = obd.OBD() 

if connection.is_connected():
    print("Connection successful")

    # Gets all supported commands/PIDs
    supported_commands = connection.supported_commands
    
    print("\nSupported PID's:")
    for command in supported_commands:
        print(f"* {command.name}")

    # You can specifically check for a command's support like this:
    # is_rpm_supported = connection.supports(obd.commands.RPM)
    # print(f"\nIs RPM supported? {is_rpm_supported}")
else:
    print("Connection failed.")