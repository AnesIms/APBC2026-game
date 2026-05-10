# Milestone 1: Functional Baseline

## Goal

Create a first working version of our robot that can be loaded by the simulator, returns valid moves, and plays several rounds without technical errors.

The bot does **not** need to be optimized yet.  
The main goal is that we have a stable baseline that we can observe, test, and improve later.


## Work split

### Person 1: Baseline Bot

**Goal:**  
Create the first version of our own robot.

**Focus:**

- create our robot file and player class,
- make sure the bot can be imported by the simulator,
- return valid moves,
- move roughly toward the gold pot,
- avoid obvious visible walls,
- use the example bots as a starting point,
- keep the code structure simple enough to improve later.

**Expected result:**  
A first playable bot that works technically and can serve as our baseline.

---

### Person 2: Visualization / Replay

**Goal:**  
Make game runs easier to inspect visually.

**Focus:**

- check how the existing `Illustrator` class is used,
- find out how to create a `.gif` or other visual replay,
- test the visualization with existing bots,
- make sure robots, walls, gold pots, mines, and movement are visible,
- document how to generate a replay.

**Expected result:**  
We can create a visual replay of a game instead of only reading the terminal output.

---

### Person 3: Evaluation / Test Runner

**Goal:**  
Create a basic way to evaluate whether our bot improves.

**Focus:**

- run several games automatically,
- use different random seeds,
- collect basic results,
- compare our bot against the provided example bots,
- record useful metrics such as final gold, winner, health, and crashes if possible.

**Expected result:**  
We have a simple testing setup that allows us to compare bot versions more objectively.

---

## Milestone 1 outcome

At the end of this milestone, we should have:

- one working baseline bot,
- a way to visualize game runs,
- a basic way to test several runs,
- a shared starting point for later improvements.


# Milestone 2: Individual Strategy Bots

## Goal

At the end of this milestone, we should have three different strategy bots that can be compared against each other and against the example bots. From these bots, we can later identify which behaviors work best and combine the strongest ideas.

### Strategy 1: XAE-12-S1.py (S1 for Strategy 1)

S1 remembers the map during the game, explores unknown areas preferably in the direction of the current gold pot, and uses BFS to find known paths to the gold. If a reasonable gold path is known, the bot sprints with multiple bought moves toward the gold, as long as the cost is worth it compared to the pot value and a small gold reserve remains.

### Strategy 2: (Name suggestion: XAE-12-S2.py)

Strategy idea:

### Strategy 3: (Name suggestion: XAE-12-S3.py)

Strategy idea:

---

## Milestone 2 outcome

At the end of this milestone, we should have:

- three different strategy bots
- a short written explanation for each strategy
- ideas for combining the best parts into a stronger future bot
- 
