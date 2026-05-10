## Usage

The automted.RobotTest.py can run x amount of games with x amount of rounds and keep track of how many moves each robot made on average per game and who was the winner of each game. The final output is an overview of of all game results.

Inside the script at line 30, you can add your robot. The key will be the name used for the result print-out and the value is the file name of your robot without .py

The script_dir is the directory from which the code is being executed. If you plan on moving the automated script, ensure that you change script_dir and robots_dir accordingly at line 36 and 37.

## Execution
```
python automated_RobotTest.py --map Game/Maps/maze_map.dat --number 100 --games 10
```

## Example Result

Starting 20 games silently... Please wait.

--- STATISTICAL ANALYSIS ---
Test_Erratic: 2 wins (10.0%) | Avg Moves per Game: 100.0
Beatme_SillyScout: 10 wins (50.0%) | Avg Moves per Game: 19.2
Adlhartm_Naive: 8 wins (40.0%) | Avg Moves per Game: 307.4
Draws/Ties: 0 games (0.0%)

