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
