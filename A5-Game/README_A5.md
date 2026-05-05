# A5-Game: Robot Race

Welcome to the APBC Robot Race project.

In this assignment, you will work in teams and implement your own robot player for a grid-based game. Your robot should collect as much gold as possible while navigating through a maze and competing against other teams.

## Teamwork

- You will work in teams of **2-3 students**.
- Each team develops its bot in its **own fork** of the class repository.
- Each student should contribute through GitHub:
  - create at least one issue
  - work in their own branch
  - open a pull request inside the team fork
  - review a teammate's pull request

## Repository structure

The official class repository is:

```bash
git@github.com:TBIAPBC/APBC2026.git
```

The game project is in:

```text
A5-Game/
```

Inside `A5-Game`, you will find:

- a `Game/` subfolder with the game engine
- example bots
- maps
- folders for team submissions

## Forking the repository

One member of each team should:

1. Fork the class repository on GitHub.
2. Add the other team members as collaborators to the fork.

If you use the GitHub CLI, the fork can also be created from the command line:

```bash
gh repo fork TBIAPBC/APBC2026 --clone=false
```

Then collaborators can be added in the GitHub web interface in:

- `Settings`
- `Collaborators`
- `Add people`

After that, each team member should clone the **team fork**, not the official repository:

```bash
git clone git@github.com:TEAM-OWNER/APBC2026.git
cd APBC2026
```

Then add the official class repository as `upstream`:

```bash
git remote add upstream git@github.com:TBIAPBC/APBC2026.git
```

Check that both remotes are configured:

```bash
git remote -v
```

You should see:

- `origin` -> your team fork
- `upstream` -> the official class repository

## Starting work on a round

Before each round, first download the newest official branches:

```bash
git fetch upstream
```

Create your local branch for the round from the official branch:

```bash
git checkout -b Round_1_game upstream/Round_1_game
```

Push that branch to your team fork:

```bash
git push -u origin Round_1_game
```

Replace `Round_1_game` with the actual round branch name when needed.

## Recommended team workflow

Work in small branches inside your team fork.

Example:

```bash
git checkout Round_1_game
git pull origin Round_1_game
git checkout -b improve-greedy-strategy
```

After making changes:

```bash
git status
git add A5-Game/teams/team_name/your_bot.py
git commit -m "Improve greedy movement"
git push -u origin improve-greedy-strategy
```

Then:

1. Open a pull request in your **team fork**
2. Ask a teammate to review it
3. Merge it into your team's round branch

When your team is ready, open **one final pull request** from your team fork into the official round branch.

## Important rule

Only code that is **merged into the official round branch** is part of that round.

## Where your team should work

Your team should modify only its own files and folders.

Do **not**:

- edit another team's bot
- change the game engine unless explicitly asked
- change the round setup

## Installing dependencies

The game uses Python 3.

Install the required packages with:

```bash
python3 -m pip install numpy matplotlib pillow
```

If you are using Conda, you can also use:

```bash
conda install numpy matplotlib pillow
```

## Running the game locally

From the `A5-Game` directory, you can run:

```bash
cd A5-Game/Game
python3 runRobotRace.py --map Maps/maze_map.dat --number 100
```

Other useful examples:

```bash
cd A5-Game/Game
python3 runRobotRace.py --map Maps/floodfill_map.dat --number 200
python3 runRobotRace.py --number 100 --density 0.3
python3 runRobotRace.py --map Maps/maze_map.dat --number 100 --viz race.gif
```

## Visualization

To save a visualization:

```bash
cd A5-Game/Game
python3 runRobotRace.py --map Maps/maze_map.dat --number 100 --viz race.gif
```

This saves the game as a file after the simulation finishes.

## What your bot has to implement

Each bot is a Python class.

The key methods are:

- `reset(self, player_id, max_players, width, height)`
- `round_begin(self, r)`
- `move(self, status)`

Optional:

- `set_mines(self, status)`

For the basic version of the project, your bot only needs to return moves.

## Submission format

Your team should provide a Python module with your robot implementation.

The module should define a variable called:

```python
players = [MyRobot()]
```

or more generally:

```python
players = [NaiveRobot(), SmarterRobot()]
```

## Strategy advice

A good first bot:

- avoids walls
- moves toward the gold pot
- uses only one move per round

Later improvements can include:

- remembering the map
- path planning
- collision avoidance
- better gold-cost tradeoffs

## Before each round, check

- Are we on the correct round branch?
- Did we pull from `upstream`?
- Did we push our final changes to the team fork?
- Did we open the final PR into the official round branch?
- Does the bot run without crashing?
- Did we change only our own team files?

## Questions

If something about the game engine, GitHub workflow, or round submission is unclear, ask early rather than waiting until the deadline.
