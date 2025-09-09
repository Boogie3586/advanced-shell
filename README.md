# Advanced Shell Simulation - Deliverable 1

## Overview
This project implements a **basic custom shell** that simulates a Unix-like operating system environment. It accepts user commands, manages processes, and provides basic job control functionality. This is **Deliverable 1** of a four-part project, focusing on **Basic Shell Implementation and Process Management**.

## Features
- **Built-in Commands**:
  - `cd [directory]`: Change working directory
  - `pwd`: Print current working directory
  - `exit`: Terminate the shell
  - `echo [text]`: Print text to terminal
  - `clear`: Clear the screen
  - `ls`: List files in current directory
  - `cat [filename]`: Display file contents
  - `mkdir [directory]`: Create new directory
  - `rmdir [directory]`: Remove empty directory
  - `rm [filename]`: Delete file
  - `touch [filename]`: Create or update a file
  - `kill [pid]`: Terminate a process by PID

- **Process Management and Job Control**:
  - Run processes in **foreground** and **background** (`&`)
  - Track and manage running jobs
  - `jobs`: List background jobs
  - `fg [job_id]`: Bring job to foreground
  - `bg [job_id]`: Resume job in background

## How to Run
1. Clone this repository:
   ```bash
   git clone https://github.com/your-username/advanced-shell.git
   cd advanced-shell
2. Make the shell script executable
  ```bash
 chmod +x myshell.py.

3. Start the shell:
```bash
./myshell.py

4. Example Usage
myshell> pwd
/home/user/projects

myshell> ls
myshell.py  README.md

myshell> sleep 10 &
[1] 1234   # Job ID and PID

myshell> jobs
[1] Running   sleep 10 &

myshell> fg 1
