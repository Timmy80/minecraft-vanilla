#!/bin/bash

# Save minecraft world
minecraft command "save-all"

# Clean old minecraft logs
find /minecraft/server/logs -mtime +20 -type f -delete

# Clean old backup file
find /minecraft/backup -mtime +40 -type f -delete


# End of script
