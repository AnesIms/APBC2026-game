# XAE-12-Team.py
#
# Team bot scaffold for the two-player tournament setup.
#
# Contains two independent Player objects in one file:
#   1. StrategyFiveBot       = current S5 placeholder / main bot
#   2. StrategyThreeOneBot   = optimized S3_1 candidate / second bot
#
# Tomorrow: replace only the StrategyFiveBot class with the final improved S5
# from the teammate, then keep the final players list at the bottom.
#
# Important: runRobotRace.py / automated_RobotTest.py will still see these as
# two separate players because the module-level players list contains two objects.

from Game.game_utils import Direction as D, Map, TileStatus
from Game.player_base import Player
from collections import deque
import math

try:
    import current_team_params as team_params
except ImportError:
    team_params = None

TEAM_GOLD_MARGIN = getattr(team_params, "TEAM_GOLD_MARGIN", 3)

# Optional parameter file used by optimization_runner.py.
# If current_bot_params.py is not present, the class defaults below are used.
try:
    import current_bot_params as bot_params
except ImportError:
    bot_params = None


TEAM_MAP = None
TEAM_POSITIONS = {}

def ensure_team_map(width, height):
    global TEAM_MAP

    if TEAM_MAP is None:
        TEAM_MAP = Map(width, height)

    return TEAM_MAP


def share_visible_map(status):
    """
    Write all visible known tiles into the shared team map.
    Unknown tiles are ignored, so known information is not overwritten.
    """
    team_map = ensure_team_map(status.map.width, status.map.height)

    for x in range(team_map.width):
        for y in range(team_map.height):
            if status.map[x, y].status != TileStatus.Unknown:
                team_map[x, y].status = status.map[x, y].status


def import_team_map(bot):
    """
    Copy shared team-map knowledge into this bot's own remembered map.
    """
    global TEAM_MAP

    if TEAM_MAP is None:
        return

    for x in range(TEAM_MAP.width):
        for y in range(TEAM_MAP.height):
            if TEAM_MAP[x, y].status != TileStatus.Unknown:
                bot.ourMap[x, y].status = TEAM_MAP[x, y].status



class StrategyFiveBot(Player):
    """
    Adaptive gold-chasing bot with three strategies that activate in sequence.

    Strategies:
        blind_chaser  — default; sprints aggressively for every pot.
        camping       — activates after LOSING_STREAK_THRESHOLD consecutive
                        losing pots; stalks the gold and grabs at the last moment.
        rivalry       — activates if camping also fails over STRATEGY_PATIENCE pots;
                        competes directly using full ETA-based sprint calculations.

    Transitions:
        blind_chaser → rivalry    if the bot has spent 500 rounds in blind_chaser
                                  and is no longer in 1st place (or drops from 1st).
        blind_chaser → camping    after 3 consecutive losing pots, or immediately
                                  if a single round causes a 2-rank drop.
        camping      → rivalry    if average rank over STRATEGY_PATIENCE pots
                                  remains at or below LOSING_RANK_THRESHOLD.
        camping      → rivalry    emergency override if score gap to leader exceeds
                                  RIVALRY_SCORE_MARGIN (is_forced_rivalry).

    Fallback when not chasing:
        - If a path to gold exists but was declined: move to spawn-positioning
          target (opposite side of map from current gold, near center).
        - If no path to gold exists at all (blind_chaser only): explore toward
          the nearest frontier tile bordering unknown map area.
        Fallback targets are locked for the entire pot lifetime to prevent
        oscillation from round-to-round re-evaluation.
    """

    DEFAULT_WALK_SPEED = 2.0
    DEFAULT_SPRINT_SPEED = 6.0
    DEFAULT_SPRINT_RANGE = 6.0

    LOW_GOLD_RECOVERY_THRESHOLD = 10

    MAX_BURST_MOVES = 5
    GOLD_SPEND_FRACTION = 0.25
    MINIMUM_GOLD_RESERVE = 20
    
    HIGH_BUDGET_THRESHOLD = 100
    MIN_PROFIT_NORMAL = 30
    MIN_PROFIT_RIVALRY = 0

    GOLD_PATH_FACTOR = 2.0
    GOLD_PATH_BONUS = 5

    RIVALRY_SCORE_MARGIN = 500
    RIVALRY_MAX_RANK = 1

    STALK_DISTANCE = 1

    LOSING_RANK_THRESHOLD = 3
    LOSING_STREAK_THRESHOLD = 5
    STRATEGY_PATIENCE = 6

    UNWINNABLE_ETA_RATIO = 0.7
    UNWINNABLE_DISTANCE_RATIO = 1

    DISTANCE_CUTOFF = 0.90
    LEADER_HISTORY_MAX_AGE = 5

    STATIONARY_DISTANCE_THRESHOLD = 0
    STATIONARY_OBSERVATION_THRESHOLD = 5
    STATIONARY_MAX_AGE = 30
    STATIONARY_SPAWN_BLOCK_RADIUS = 4
    STATIONARY_SPAWN_BLOCK_PENALTY = 4.0

    def reset(self, player_id, max_players, width, height):
        self.player_name = "XAE-12 S5"
        self.ourMap = Map(width, height)
        ensure_team_map(width, height)
        self.current_enemies = set()
        self.enemy_history = {}
        self.stationary_enemy_positions = []
        self.player_id = player_id
        self.max_players = max_players
        self.estimated_scores = {i: 0 for i in range(max_players)}
        self.seen_pots = {}
        self.last_pots = {}
        self.leader_id = None
        self.leader_score = -float('inf')
        self.current_round = 0
        self.center = (width // 2, height // 2)

        self.fallback_target = None
        self.last_gold_pos = None
        self.pot_abandoned = False

        self.active_strategy = "blind_chaser"
        self.blind_chaser_rounds = 0

        self.pot_gold_id = None
        self.pot_rank_at_spawn = None
        self.pot_score_at_spawn = 0
        self.pot_was_unwinnable = False
        self.pot_spawn_round = 0

        self.losing_streak = 0
        self.last_round_rank = None

        self.camping_pots_played = 0
        self.camping_rank_sum = 0

        # ---- Stats Tracking Variables ----
        self._pot_log = []
        self._strategy_segments = [("blind_chaser", 0)]
        self._total_victories = 0
        self._total_unwinnable = 0

    def round_begin(self, r):
        self.current_round = r
        if self.active_strategy == "blind_chaser":
            self.blind_chaser_rounds += 1

    def set_mines(self, status):
        return []

    # ---- Map helpers ----

    def in_bounds(self, x, y):
        """True if (x, y) lies within the map grid."""
        return 0 <= x < self.ourMap.width and 0 <= y < self.ourMap.height

    def is_known_free(self, x, y):
        """True if (x, y) is in bounds and confirmed empty."""
        if not self.in_bounds(x, y):
            return False
        return self.ourMap[x, y].status == TileStatus.Empty

    def direction_from_to(self, start_x, start_y, target_x, target_y):
        """Return the Direction enum value for a single-step move from start to target, or None."""
        dx, dy = target_x - start_x, target_y - start_y
        for direction in D:
            dir_x, dir_y = direction.as_xy()
            if (dir_x, dir_y) == (dx, dy):
                return direction
        return None

    def count_known_free_neighbors(self, position):
        """Return the number of confirmed-empty tiles adjacent to position."""
        x, y = position
        return sum(
            1 for d in D
            if self.is_known_free(x + d.as_xy()[0], y + d.as_xy()[1])
        )


    def stationary_spawn_block_penalty(self, candidate):
        """
        Penalize fallback candidates near stationary enemies.

        This is not collision avoidance. The idea is that a stationary enemy
        may block or reduce the usefulness of nearby future gold spawn areas.
        """
        penalty = 0.0

        for enemy_pos in getattr(self, "stationary_enemy_positions", []):
            distance = max(
                abs(candidate[0] - enemy_pos[0]),
                abs(candidate[1] - enemy_pos[1])
            )

            if distance <= self.STATIONARY_SPAWN_BLOCK_RADIUS:
                penalty += (
                    self.STATIONARY_SPAWN_BLOCK_RADIUS - distance + 1
                ) * self.STATIONARY_SPAWN_BLOCK_PENALTY

        return penalty


    # ---- Pathfinding ----

    def shortest_path(self, start, goal):
        """
        BFS over known-free tiles from start to goal.

        Enemy tiles are treated as blocked for intermediate steps but not for
        the goal itself, allowing the bot to path toward a gold tile that an
        enemy is standing on.

        Returns a list of (x, y) positions including start and goal,
        or None if no path exists through currently known tiles.
        """
        queue = deque([start])
        came_from = {start: None}

        while queue:
            current = queue.popleft()
            if current == goal:
                break
            for direction in D:
                dx, dy = direction.as_xy()
                next_pos = (current[0] + dx, current[1] + dy)

                if next_pos in self.current_enemies and next_pos != goal:
                    continue
                if next_pos in came_from:
                    continue
                if not self.in_bounds(*next_pos):
                    continue
                if next_pos == goal:
                    if self.ourMap[next_pos[0], next_pos[1]].status == TileStatus.Wall:
                        continue
                elif not self.is_known_free(*next_pos):
                    continue

                came_from[next_pos] = current
                queue.append(next_pos)

        if goal not in came_from:
            return None

        path = []
        curr = goal
        while curr is not None:
            path.append(curr)
            curr = came_from[curr]
        path.reverse()
        return path

    def get_visible_enemy_paths(self, status, target):
        """Return a list of (player_id, path) for every visible enemy that has a path to target."""
        paths = []
        for other in status.others:
            if other is None:
                continue
            p = self.shortest_path((other.x, other.y), target)
            if p and len(p) > 1:
                paths.append((other.player, p))
        return paths

    def safe_path_to_moves(self, path, max_moves, enemy_paths):
        """
        Convert a planned path into a move list, stopping early if any future
        tile would be reached by an enemy at the same time or sooner.

        Returns a (possibly empty) list of Direction values.
        """
        moves = []
        path_to_walk = path[1:]
        current_node = path[0]

        for i in range(min(max_moves, len(path_to_walk))):
            next_node = path_to_walk[i]
            my_arrival_time = i + 1

            contested = any(
                next_node in e_path and e_path.index(next_node) <= my_arrival_time
                for _, e_path in enemy_paths
            )
            if contested:
                break

            direction = self.direction_from_to(
                current_node[0], current_node[1], next_node[0], next_node[1]
            )
            if direction is None:
                break

            moves.append(direction)
            current_node = next_node

        return moves

    # ---- Enemy tracking ----

    def update_enemy_tracker(self, status, gold_pos=None):
        """
        Update per-enemy history with current position, observed max burst distance,
        and simple stationary-enemy detection.

        A stationary enemy is an enemy that we repeatedly observe on the same tile.
        This will later be used for spawn-positioning, not for making the enemy harmless.
        """
        self.stationary_enemy_positions = []

        for other in status.others:
            if other is None:
                continue

            enemy_id = other.player
            current_position = (other.x, other.y)

            if enemy_id not in self.enemy_history:
                self.enemy_history[enemy_id] = {
                    "last_position": current_position,
                    "max_burst": self.DEFAULT_SPRINT_SPEED,
                    "last_seen_round": self.current_round,
                    "stationary_count": 1,
                    "stationary": False,
                }
            else:
                hist = self.enemy_history[enemy_id]
                last_position = hist["last_position"]

                distance_moved = max(
                    abs(current_position[0] - last_position[0]),
                    abs(current_position[1] - last_position[1]),
                )

                if distance_moved > hist.get("max_burst", 0):
                    hist["max_burst"] = distance_moved

                if distance_moved <= self.STATIONARY_DISTANCE_THRESHOLD:
                    hist["stationary_count"] = hist.get("stationary_count", 1) + 1
                else:
                    hist["stationary_count"] = 1

                hist["stationary"] = (
                    hist["stationary_count"] >= self.STATIONARY_OBSERVATION_THRESHOLD
                )

                hist["last_position"] = current_position
                hist["last_seen_round"] = self.current_round

            hist = self.enemy_history[enemy_id]

            if hist.get("stationary", False):
                self.stationary_enemy_positions.append(current_position)

    def calculate_enemy_eta(self, enemy_id, enemy_distance):
        """
        Estimate rounds for enemy to reach a tile at enemy_distance steps away.

        Assumes the enemy sprints their observed max_burst tiles at DEFAULT_SPRINT_SPEED,
        then walks the remainder at DEFAULT_WALK_SPEED.
        """
        hist = self.enemy_history.get(enemy_id, {})
        max_burst = hist.get("max_burst", self.DEFAULT_SPRINT_SPEED)

        if enemy_distance <= max_burst:
            return enemy_distance / self.DEFAULT_SPRINT_SPEED
        walk_dist = enemy_distance - max_burst
        return (max_burst / self.DEFAULT_SPRINT_SPEED) + (walk_dist / self.DEFAULT_WALK_SPEED)

    # ---- Score estimation ----

    def _attribute_pot(self, pot_pos, pot_value, status):
        """
        Attribute a disappeared pot to the most likely grabber.

        Priority:
            1. Our gold increased since pot spawn → we grabbed it; return (None, 0)
               so the caller skips enemy attribution.
            2. A visible enemy is standing on the pot tile → certain grab.
            3. Build an ETA-ranked candidate list from all enemies with history,
               including off-screen players using their last known position plus
               a staleness penalty of 0.5 rounds per unseen round.
            4. If no candidates exist, split the value evenly across all enemies
               so gold is not silently lost from the shadow scoreboard.

        Returns (winner_id, net_profit) or (None, 0) if we grabbed it.
        """
        our_gold_before = (self.pot_score_at_spawn if self.pot_gold_id == pot_pos
                           else self.estimated_scores[self.player_id])
        if status.gold > our_gold_before:
            return None, 0

        for other in status.others:
            if other is None:
                continue
            if (other.x, other.y) == pot_pos:
                return other.player, max(0, pot_value - status.params.cost(1))

        candidates = []
        all_enemy_ids = set(self.enemy_history.keys())
        for other in status.others:
            if other is not None:
                all_enemy_ids.add(other.player)

        for pid in all_enemy_ids:
            if any(o is not None and o.player == pid for o in status.others):
                other = next(o for o in status.others if o is not None and o.player == pid)
                start_pos = (other.x, other.y)
                staleness = 0
            else:
                hist = self.enemy_history.get(pid)
                if hist is None:
                    continue
                start_pos = hist["last_position"]
                staleness = self.current_round - hist.get("last_seen_round", self.current_round)

            path = self.shortest_path(start_pos, pot_pos)
            dist = len(path) - 1 if path is not None else (
                abs(start_pos[0] - pot_pos[0]) + abs(start_pos[1] - pot_pos[1])
            )

            eta = self.calculate_enemy_eta(pid, dist) + staleness * 0.5
            cost = status.params.cost(min(dist, 3))
            candidates.append((eta, pid, cost))

        if not candidates:
            enemy_ids = [pid for pid in self.estimated_scores if pid != self.player_id]
            if enemy_ids:
                share = max(0, pot_value) / len(enemy_ids)
                for pid in enemy_ids:
                    self.estimated_scores[pid] += share
            return None, 0

        candidates.sort(key=lambda x: x[0])
        winner_id, cost = candidates[0][1], candidates[0][2]
        return winner_id, max(0, pot_value - cost)

    def update_shadow_scoreboard(self, status):
        """
        Maintain estimated scores for all players each round.

        Tracks pot appearances and disappearances; attributes disappeared pots
        via _attribute_pot. Our own score is always overwritten with the ground-truth
        value from status.gold. Also updates leader_id and leader_score.
        """
        if status.goldPots:
            for loc, amount in status.goldPots.items():
                self.seen_pots[loc] = amount

        if self.last_pots:
            for loc, amount in self.last_pots.items():
                if not status.goldPots or loc not in status.goldPots:
                    winner, profit = self._attribute_pot(loc, amount, status)
                    if winner is not None:
                        self.estimated_scores[winner] += profit
                    if loc in self.seen_pots:
                        del self.seen_pots[loc]

        self.estimated_scores[self.player_id] = status.gold
        self.last_pots = status.goldPots.copy() if status.goldPots else {}

        self.leader_id = None
        self.leader_score = -float('inf')
        for pid, score in self.estimated_scores.items():
            if score > self.leader_score:
                self.leader_score = score
                self.leader_id = pid

    def get_my_rank(self):
        """Return our current rank (1 = first place) based on estimated scores."""
        sorted_scores = sorted(self.estimated_scores.items(), key=lambda x: x[1], reverse=True)
        for i, (pid, _) in enumerate(sorted_scores):
            if pid == self.player_id:
                return i + 1
        return self.max_players

    def is_forced_rivalry(self, current_gold):
        """True if we are dangerously behind the leader and should override camping with rivalry."""
        return (self.get_my_rank() <= self.RIVALRY_MAX_RANK and
                self.leader_score - current_gold > self.RIVALRY_SCORE_MARGIN)

    # ---- Strategy state machine ----

    def _set_strategy(self, new_strategy):
        """Helper to cleanly change strategies and log it for the summary."""
        if self.active_strategy != new_strategy:
            self.active_strategy = new_strategy
            self._strategy_segments.append((new_strategy, self.current_round))

    def _on_new_pot(self, new_gold_pos, current_score, pot_is_unwinnable=False):
        """
        Called once when a new gold pot appears.

        Resolves the previous pot: logs it into stats, increments losing_streak
        or camping counters based on end rank, then triggers a strategy escalation
        if thresholds are met.
        """
        current_rank = self.get_my_rank()

        # Log previous pot into stats
        if self.pot_gold_id is not None:
            score_gained = current_score - self.pot_score_at_spawn
            won_pot = score_gained > 0
            
            if won_pot:
                self._total_victories += 1
            if self.pot_was_unwinnable:
                self._total_unwinnable += 1

            self._pot_log.append({
                "pot_pos": self.pot_gold_id,
                "spawn_round": self.pot_spawn_round,
                "close_round": self.current_round,
                "strategy": self.active_strategy,
                "rank_at_spawn": self.pot_rank_at_spawn,
                "rank_at_close": current_rank,
                "score_gained": score_gained,
                "won": won_pot,
                "unwinnable": self.pot_was_unwinnable,
                "scoreboard": self.estimated_scores.copy()
            })

            # Check logic for progression
            if not self.pot_was_unwinnable:
                end_rank = current_rank

                if self.active_strategy == "blind_chaser":
                    if end_rank >= self.LOSING_RANK_THRESHOLD:
                        self.losing_streak += 1
                    else:
                        self.losing_streak = 0

                    if self.losing_streak >= self.LOSING_STREAK_THRESHOLD:
                        self._set_strategy("camping")
                        self.losing_streak = 0
                        self.camping_pots_played = 0
                        self.camping_rank_sum = 0

                elif self.active_strategy == "camping":
                    self.camping_pots_played += 1
                    self.camping_rank_sum += end_rank

                    if self.camping_pots_played >= self.STRATEGY_PATIENCE:
                        avg_rank = self.camping_rank_sum / self.camping_pots_played
                        if avg_rank >= self.LOSING_RANK_THRESHOLD:
                            self._set_strategy("rivalry")
                        else:
                            self.camping_pots_played = 0
                            self.camping_rank_sum = 0

        self.pot_gold_id = new_gold_pos
        self.pot_score_at_spawn = current_score
        self.pot_rank_at_spawn = current_rank
        self.pot_was_unwinnable = pot_is_unwinnable
        self.pot_spawn_round = self.current_round

    # ---- Winnability ----

    def is_pot_winnable(self, our_dist, enemy_paths, params):
        if our_dist is None or our_dist == float('inf'):
            return False
        our_sprint_eta = our_dist / self.DEFAULT_SPRINT_SPEED
        for enemy_id, enemy_path in enemy_paths:
            enemy_dist = len(enemy_path) - 1
            enemy_eta = self.calculate_enemy_eta(enemy_id, enemy_dist)
            if (enemy_eta < our_sprint_eta * self.UNWINNABLE_ETA_RATIO and
                    enemy_dist * self.UNWINNABLE_DISTANCE_RATIO <= our_dist):
                return False
        return True

    # ---- Sprint decisions ----

    def is_gold_path_reasonable(self, position, gold_position, path):
        path_length = len(path) - 1
        direct_distance = max(
            abs(gold_position[0] - position[0]),
            abs(gold_position[1] - position[1]),
        )
        return path_length <= direct_distance * self.GOLD_PATH_FACTOR + self.GOLD_PATH_BONUS


    def move_cost(self, number_of_moves):
        return number_of_moves * (number_of_moves + 1) // 2
    

    def choose_burst_length(self, path_length, gold_value, current_gold):
        """
        S3_1-style budget control:
        choose a burst length without spending too much of our gold
        or too much of the current pot value.
        """
        burst_length = 1

        for number_of_moves in range(1, min(path_length, self.MAX_BURST_MOVES) + 1):
            cost = self.move_cost(number_of_moves)

            if cost > current_gold - self.MINIMUM_GOLD_RESERVE:
                break

            if cost > gold_value * self.GOLD_SPEND_FRACTION:
                break

            burst_length = number_of_moves

        return burst_length
    

    def calculate_sprint_decision_simple(self, path_to_gold, enemy_paths, current_gold, gold_value, params):
        distance_to_gold = len(path_to_gold) - 1

        if distance_to_gold <= 0:
            return True, 0

        closest_enemy_distance = min(
            (len(ep) - 1 for _, ep in enemy_paths),
            default=float("inf")
        )

        # If a visible enemy is clearly closer, do not waste gold in blind_chaser.
        if closest_enemy_distance < distance_to_gold * self.DISTANCE_CUTOFF:
            return False, 0

        full_sprint_cost = params.cost(distance_to_gold)

        if full_sprint_cost <= current_gold and (gold_value - full_sprint_cost) > 30:
            return True, distance_to_gold

        return True, min(5, distance_to_gold)

    def calculate_sprint_decision(self, path_to_gold, enemy_paths, current_gold, gold_value, rivalry_mode, params):
        distance_to_gold = len(path_to_gold) - 1
        if distance_to_gold <= 0:
            return True, 0

        fastest_enemy_eta = float('inf')
        closest_enemy_distance = float('inf')

        for enemy_id, enemy_path in enemy_paths:
            enemy_distance = len(enemy_path) - 1
            enemy_eta = self.calculate_enemy_eta(enemy_id, enemy_distance)
            if enemy_eta < fastest_enemy_eta:
                fastest_enemy_eta = enemy_eta
            if enemy_distance < closest_enemy_distance:
                closest_enemy_distance = enemy_distance

        if closest_enemy_distance < distance_to_gold * self.DISTANCE_CUTOFF:
            if fastest_enemy_eta < distance_to_gold / self.DEFAULT_SPRINT_SPEED:
                return False, 0

        our_normal_eta = distance_to_gold / self.DEFAULT_WALK_SPEED

        if fastest_enemy_eta <= our_normal_eta:
            target_eta = max(1.0, fastest_enemy_eta - 1.0)
            desired_moves = min(math.ceil(distance_to_gold / target_eta), distance_to_gold)
            sprint_cost = params.cost(desired_moves)
            eta_rounds = math.ceil(distance_to_gold / max(1, desired_moves))
            decay_penalty = eta_rounds * params.goldPerRound if params.goldDecrease else 0
            expected_profit = (gold_value - decay_penalty) - sprint_cost

            min_profit = self.MIN_PROFIT_RIVALRY if rivalry_mode else self.MIN_PROFIT_NORMAL
            if expected_profit >= min_profit and sprint_cost <= current_gold:
                return True, desired_moves
            return False, 0

        # No enemy seems faster:
        # use S3_1-style controlled burst instead of fixed aggressive bursts.
        burst_length = self.choose_burst_length(
            distance_to_gold,
            gold_value,
            current_gold
        )

        return True, min(burst_length, distance_to_gold)

    # ---- Camping helpers ----

    def is_safe_to_wait(self, current_pos, gold_pos, status, my_dist=None):
        if my_dist is None:
            my_path = self.shortest_path(current_pos, gold_pos)
            if not my_path:
                return False
            my_dist = len(my_path) - 1

        my_eta = max(my_dist, self.STALK_DISTANCE) / self.DEFAULT_WALK_SPEED

        for other in status.others:
            if other is None:
                continue
            enemy_path = self.shortest_path((other.x, other.y), gold_pos)
            enemy_dist = len(enemy_path) - 1 if enemy_path else float('inf')
            max_burst = self.enemy_history.get(other.player, {}).get("max_burst", self.DEFAULT_SPRINT_SPEED)
            if enemy_dist <= math.ceil(max_burst):
                return False
            if self.calculate_enemy_eta(other.player, enemy_dist) <= my_eta:
                return False
        return True

    def is_gold_in_snatch_danger(self, gold_pos, status):
        if status.goldPotRemainingRounds <= 1:
            return True
        for other in status.others:
            if other is None:
                continue
            enemy_path = self.shortest_path((other.x, other.y), gold_pos)
            if not enemy_path:
                continue
            enemy_dist = len(enemy_path) - 1
            max_burst = self.enemy_history.get(other.player, {}).get("max_burst", self.DEFAULT_SPRINT_SPEED)
            if (enemy_dist <= max_burst and
                    self.estimated_scores.get(other.player, 100) >= status.params.cost(enemy_dist)):
                return True
        return False

    # ---- Fallback positioning ----

    def get_fallback_path(self, current_pos, gold_pos):
        center_x, center_y = self.center
        gold_x, gold_y = gold_pos
        away_x, away_y = center_x - gold_x, center_y - gold_y
        target = (
            max(0, min(self.ourMap.width - 1, round(center_x + 0.5 * away_x))),
            max(0, min(self.ourMap.height - 1, round(center_y + 0.5 * away_y))),
        )

        best_candidate, best_score = None, float('inf')
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if not self.is_known_free(x, y) or (x, y) in self.current_enemies:
                    continue
                candidate = (x, y)

                score = (
                    max(abs(x - target[0]), abs(y - target[1]))
                    + 0.4 * max(abs(x - current_pos[0]), abs(y - current_pos[1]))
                    - 1.0 * self.count_known_free_neighbors(candidate)
                    + self.stationary_spawn_block_penalty(candidate)
                )
                if score < best_score:
                    best_score = score
                    best_candidate = candidate

        return self.shortest_path(current_pos, best_candidate) if best_candidate else None

    def get_best_frontier_target(self, pos, gold_pos):
        frontiers = []
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if self.ourMap[x, y].status != TileStatus.Empty:
                    continue
                for d in D:
                    dx, dy = d.as_xy()
                    nx, ny = x + dx, y + dy
                    if self.in_bounds(nx, ny) and self.ourMap[nx, ny].status == TileStatus.Unknown:
                        frontiers.append((x, y))
                        break

        best_path = None
        best_score = (float('inf'), float('inf'), float('inf'))
        for frontier in frontiers:
            path = self.shortest_path(pos, frontier)
            if path is None or len(path) < 2:
                continue
            dist_to_gold = max(abs(gold_pos[0] - frontier[0]), abs(gold_pos[1] - frontier[1]))
            score = (len(path) - 1 + 0.5 * dist_to_gold, frontier[0], frontier[1])
            if score < best_score:
                best_score = score
                best_path = path

        return best_path

    # ---- Main orchestrator ----

    def move(self, status):
        self.update_shadow_scoreboard(status)
        if not status.goldPots:
            return []

        current_gold_pos = next(iter(status.goldPots))
        if current_gold_pos != self.pot_gold_id:
            self.pot_abandoned = False
            _our_path = self.shortest_path((status.x, status.y), current_gold_pos)
            _our_dist = len(_our_path) - 1 if _our_path else None
            _spawn_enemy_paths = self.get_visible_enemy_paths(status, current_gold_pos)
            _unwinnable = not self.is_pot_winnable(_our_dist, _spawn_enemy_paths, status.params)
            self._on_new_pot(current_gold_pos, status.gold, pot_is_unwinnable=_unwinnable)

        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if status.map[x, y].status != TileStatus.Unknown:
                    self.ourMap[x, y].status = status.map[x, y].status

        # Share this bot's visible map with the team and import teammate knowledge
        share_visible_map(status)
        import_team_map(self)

        if status.health < 30:
            return []

        current_pos = (status.x, status.y)
        gold_pos = next(iter(status.goldPots))

        TEAM_POSITIONS["S5"] = current_pos

        # Low-gold recovery:
        # If we are almost broke, only spend gold when the pot is truly reachable
        # with a very short known path. Otherwise, wait and rebuild gold.
        if status.gold < self.LOW_GOLD_RECOVERY_THRESHOLD:
            emergency_path_to_gold = self.shortest_path(current_pos, gold_pos)

            if emergency_path_to_gold is None:
                return []

            emergency_distance = len(emergency_path_to_gold) - 1

            if emergency_distance > 1:
                return []
            

        self.current_enemies = set()
        for other in status.others:
            if other is not None:
                self.current_enemies.add((other.x, other.y))

        self.update_enemy_tracker(status, gold_pos)

        effective_strategy = self.active_strategy
        if effective_strategy == "camping" and self.is_forced_rivalry(status.gold):
            effective_strategy = "rivalry"

        current_rank = self.get_my_rank()
        
        if (self.active_strategy == "blind_chaser"
                and self.blind_chaser_rounds >= 500
                and current_rank > 1):
            self._set_strategy("rivalry")
            effective_strategy = "rivalry"
            self.losing_streak = 0
            self.camping_pots_played = 0
            self.camping_rank_sum = 0
            
        #elif (self.active_strategy == "blind_chaser"
         #       and self.last_round_rank is not None
          #      and current_rank - self.last_round_rank >= 2):
           # self._set_strategy("camping")
            #effective_strategy = "camping"
            #self.losing_streak = 0
            #self.camping_pots_played = 0
            #self.camping_rank_sum = 0
            
        self.last_round_rank = current_rank

        path_to_gold = self.shortest_path(current_pos, gold_pos)
        distance_to_gold = len(path_to_gold) - 1 if path_to_gold else float('inf')
        enemy_paths = self.get_visible_enemy_paths(status, gold_pos)

        chasing_gold = False
        num_moves = 0
        best_path = [current_pos]

        if path_to_gold and not self.pot_abandoned:
            gold_value = status.goldPots[gold_pos]

            if effective_strategy == "blind_chaser":
                if distance_to_gold / 5 <= status.goldPotRemainingRounds:
                    chasing_gold, num_moves = self.calculate_sprint_decision_simple(
                        path_to_gold, enemy_paths, status.gold, gold_value,
                        params=status.params
                    )
                    if chasing_gold:
                        best_path = path_to_gold

            elif effective_strategy == "rivalry":
                if self.is_gold_path_reasonable(current_pos, gold_pos, path_to_gold):
                    chasing_gold, num_moves = self.calculate_sprint_decision(
                        path_to_gold, enemy_paths, status.gold, gold_value,
                        rivalry_mode=True, params=status.params
                    )
                    if chasing_gold:
                        best_path = path_to_gold

            else:
                if self.is_gold_path_reasonable(current_pos, gold_pos, path_to_gold):
                    if distance_to_gold == 0:
                        chasing_gold = True
                        best_path = path_to_gold
                        num_moves = 0
                    elif distance_to_gold <= self.STALK_DISTANCE:
                        chasing_gold = True
                        best_path = path_to_gold
                        num_moves = distance_to_gold if self.is_gold_in_snatch_danger(gold_pos, status) else 0
                    elif self.is_safe_to_wait(current_pos, gold_pos, status, my_dist=distance_to_gold):
                        chasing_gold = True
                        best_path = path_to_gold
                        num_moves = min(2, distance_to_gold - self.STALK_DISTANCE)
                    else:
                        chasing_gold, num_moves = self.calculate_sprint_decision(
                            path_to_gold, enemy_paths, status.gold, gold_value,
                            rivalry_mode=False, params=status.params
                        )
                        if chasing_gold:
                            best_path = path_to_gold

            if not chasing_gold:
                self.pot_abandoned = True

        if not chasing_gold:
            if gold_pos != self.last_gold_pos:
                self.fallback_target = None
                self.last_gold_pos = gold_pos

            if self.fallback_target:
                if current_pos == self.fallback_target:
                    self.fallback_target = None
                elif not self.shortest_path(current_pos, self.fallback_target):
                    self.fallback_target = None

            if not self.fallback_target:
                if path_to_gold is not None:
                    fp = self.get_fallback_path(current_pos, gold_pos)
                    if fp and len(fp) > 1:
                        self.fallback_target = fp[-1]
                elif effective_strategy == "blind_chaser":
                    fp = self.get_best_frontier_target(current_pos, gold_pos)
                    if fp and len(fp) > 1:
                        self.fallback_target = fp[-1]

            if self.fallback_target:
                path_to_fallback = self.shortest_path(current_pos, self.fallback_target)
                if path_to_fallback and len(path_to_fallback) > 1:
                    best_path = path_to_fallback
                    num_moves = 2

        target_node = best_path[-1] if best_path else current_pos
        collision_enemy_paths = self.get_visible_enemy_paths(status, target_node)
        return self.safe_path_to_moves(best_path, num_moves, collision_enemy_paths)

    # ---- Summary Output ----

    def game_over(self):
        """Called by the framework at the end of the game. Flushes the summary."""
        self._write_summary()

    def _write_summary(self):
        """Write a human-readable game summary to stalker_hunter_summary.txt."""
        lines = []
        sep  = "=" * 72
        thin = "-" * 72

        lines.append(sep)
        lines.append("  STALKERHUNTER — GAME SUMMARY")
        lines.append(sep)

        lines.append("")
        lines.append("STRATEGY TIMELINE")
        lines.append(thin)
        segments = getattr(self, '_strategy_segments', [])
        for i, (strat, start) in enumerate(segments):
            end_round = segments[i + 1][1] - 1 if i + 1 < len(segments) else getattr(self, 'current_round', 0)
            duration = end_round - start + 1
            if i + 1 < len(segments):
                switch_rank = None
                switch_round = segments[i + 1][1]
                for entry in reversed(getattr(self, '_pot_log', [])):
                    if entry["close_round"] <= switch_round:
                        switch_rank = entry["rank_at_close"]
                        break
                lines.append(
                    f"  [{strat:<14}]  rounds {start:>4} – {end_round:>4}"
                    f"  ({duration:>3} rounds)"
                    f"  → switched to {segments[i+1][0]}"
                    f"  at rank {switch_rank if switch_rank is not None else '?'}"
                )
            else:
                lines.append(
                    f"  [{strat:<14}]  rounds {start:>4} – {end_round:>4}"
                    f"  ({duration:>3} rounds)  [final strategy]"
                )

        total_pots = len(getattr(self, '_pot_log', []))
        final_rank = self.get_my_rank() if hasattr(self, 'get_my_rank') else "?"
        final_score = getattr(self, 'estimated_scores', {}).get(getattr(self, 'player_id', None), 0)

        lines.append("")
        lines.append("OVERALL STATS")
        lines.append(thin)
        lines.append(f"  Total pots played  : {total_pots}")
        total_victories = getattr(self, '_total_victories', 0)
        total_unwinnable = getattr(self, '_total_unwinnable', 0)
        lines.append(f"  Victories (won pot): {total_victories}"
                     f"  ({100*total_victories//total_pots if total_pots else 0}%)")
        lines.append(f"  Unwinnable pots    : {total_unwinnable}"
                     f"  ({100*total_unwinnable//total_pots if total_pots else 0}%)")
        max_players = getattr(self, 'max_players', "?")
        lines.append(f"  Final rank         : {final_rank} / {max_players}")
        lines.append(f"  Final score        : {final_score}")

        lines.append("")
        lines.append("FINAL SHADOW SCOREBOARD")
        lines.append(thin)

        player_names = getattr(self, "player_names", {})

        sorted_scores = sorted(
            getattr(self, 'estimated_scores', {}).items(),
            key=lambda x: x[1],
            reverse=True
        )

        for rank_i, (pid, score) in enumerate(sorted_scores, 1):
            marker = " ◄ us" if pid == getattr(self, 'player_id', None) else ""
            name = player_names.get(pid, f"player {pid}")
            lines.append(f"  #{rank_i}  {name:<20} : {score}{marker}")

        lines.append("")
        lines.append("PER-STRATEGY BREAKDOWN")
        lines.append(thin)
        for strat in ("blind_chaser", "camping", "rivalry"):
            entries = [e for e in getattr(self, '_pot_log', []) if e["strategy"] == strat]
            if not entries:
                continue
            wins  = sum(1 for e in entries if e["won"])
            unwon = sum(1 for e in entries if e["unwinnable"])
            total = len(entries)
            avg_rank = sum(e["rank_at_close"] for e in entries) / total if total > 0 else 0
            lines.append(f"  {strat:<14}  pots={total:>3}  wins={wins:>3}"
                         f"  unwinnable={unwon:>3}  avg_rank={avg_rank:.2f}")

        lines.append("")
        lines.append("POT-BY-POT DETAIL")
        lines.append(thin)
        lines.append(
            f"  {'#':>3}  {'pos':>12}  {'rnd':>4}  {'strat':<14}"
            f"  {'rank_s':>6}  {'rank_e':>6}  {'+score':>7}"
            f"  {'won':>3}  {'unwn':>4}"
        )
        lines.append("  " + "-" * 68)
        for i, entry in enumerate(getattr(self, '_pot_log', []), 1):
            pos_str = f"({entry['pot_pos'][0]},{entry['pot_pos'][1]})"
            rnd_str = (f"{entry['spawn_round']}–{entry['close_round']}"
                       if entry['spawn_round'] is not None else f"?–{entry['close_round']}")
            lines.append(
                f"  {i:>3}  {pos_str:>12}  {rnd_str:>4}  {entry['strategy']:<14}"
                f"  {entry['rank_at_spawn']:>6}  {entry['rank_at_close']:>6}"
                f"  {entry['score_gained']:>7}"
                f"  {'YES' if entry['won'] else 'no':>3}"
                f"  {'UNWN' if entry['unwinnable'] else '':>4}"
            )
            sb = entry.get("scoreboard", {})
            sb_sorted = sorted(sb.items(), key=lambda x: x[1], reverse=True)
            sb_str = "  ".join(
                f"p{pid}={'*' if pid == getattr(self, 'player_id', None) else ''}{score}"
                for pid, score in sb_sorted
            )
            lines.append(f"      scoreboard: {sb_str}")

        lines.append("")
        lines.append(sep)

        try:
            with open("strategy_S5_stats.txt", "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
        except Exception as e:
            print("Could not write stats file:", e)


# Allow optimization_runner.py to override selected class parameters without
# editing this bot file for every test run.
TUNABLE_PARAMETERS = [
    "LOW_GOLD_RECOVERY_THRESHOLD",
    "MAX_BURST_MOVES",
    "GOLD_SPEND_FRACTION",
    "MINIMUM_GOLD_RESERVE",
    "HIGH_BUDGET_THRESHOLD",
    "MIN_PROFIT_NORMAL",
    "MIN_PROFIT_RIVALRY",
    "GOLD_PATH_FACTOR",
    "GOLD_PATH_BONUS",
    "RIVALRY_SCORE_MARGIN",
    "STALK_DISTANCE",
    "LOSING_RANK_THRESHOLD",
    "LOSING_STREAK_THRESHOLD",
    "STRATEGY_PATIENCE",
    "UNWINNABLE_ETA_RATIO",
    "UNWINNABLE_DISTANCE_RATIO",
    "DISTANCE_CUTOFF",
    "STATIONARY_OBSERVATION_THRESHOLD",
    "STATIONARY_SPAWN_BLOCK_RADIUS",
    "STATIONARY_SPAWN_BLOCK_PENALTY",
]

if bot_params is not None:
    for parameter_name in TUNABLE_PARAMETERS:
        if hasattr(bot_params, parameter_name):
            setattr(StrategyFiveBot, parameter_name, getattr(bot_params, parameter_name))


# ============================================================
# Second team bot: optimized S3_1
# ============================================================

from Game.game_utils import Direction as D 
from Game.game_utils import Map, TileStatus 
from Game.player_base import Player
from collections import deque
import math

# Optional parameter file used by optimization_runner_S3_1.py.
# If current_s31_params.py is not present, the class defaults below are used.
try:
    import current_s31_params as bot_params
except ImportError:
    bot_params = None
# Import movement directions, map handling, tile information (is the tile a wall, unknown ...), and the base Player class


# Main behavior priority:
# 1. Update internal map and opponent information.
# 2. If health is too low, stay still.
# 3. If a reasonable path to gold is known, decide whether to sprint.
# 4. If sprinting is not worth it, reposition for the next spawn.
# 5. If no gold path is known, explore useful frontier fields.
# 6. Otherwise, stay still.



class StrategyThreeOneBot(Player):
    # Tunable parameters for later 
    MAX_BURST_MOVES = 5
    GOLD_SPEND_FRACTION = 0.25
    MINIMUM_GOLD_RESERVE = 20

    DEFAULT_ENEMY_SPEED = 2.0
    HIGH_BUDGET_THRESHOLD = 100
    HIGH_BUDGET_BURST = 4

    MIN_PROFIT_NORMAL = 1
    MIN_PROFIT_RIVALRY = 0

    FRONTIER_GOLD_WEIGHT = 0.5
    GOLD_PATH_FACTOR = 2.0
    GOLD_PATH_BONUS = 5

    RIVALRY_SCORE_MARGIN = 25

    # If a rival is estimated to be leading, we take slightly more risk.
    LOST_POT_ENEMY_DISTANCE = 2

    
    def reset(self, player_id, max_players, width, height):
        self.player_name = "XAE-12 S3_1"
        self.ourMap = Map(width, height)
        ensure_team_map(width, height)
        self.current_enemies = set()
        self.enemy_history = {}

        self.player_id = player_id
        self.max_players = max_players
        self.estimated_scores = {i: 0 for i in range(max_players)}
        self.last_pots = {}

        # Called once at the beginning of a game.
        # ourMap is our remembered map.
        # It starts mostly unknown, but during the game we continuously update it
        # with all visible fields from the current status.
    
    def round_begin(self, r):
        pass

    def set_mines(self, status):
        return []


# ============================================================
# Basic geometry / map helpers
# ============================================================

    def in_bounds(self, x, y):
    # Return True if the coordinate is inside the map.
        return 0 <= x < self.ourMap.width and 0 <= y < self.ourMap.height

    def is_known_free(self, x, y):
    # Return True if the field is inside the map and known to be empty
        if not self.in_bounds(x, y):
            return False

        return self.ourMap[x, y].status == TileStatus.Empty

    def direction_from_to(self, start_x, start_y, target_x, target_y):
    # Convert two neighboring coordinates into the corresponding movement direction.
        dx = target_x - start_x
        dy = target_y - start_y

        for direction in D:
            dir_x, dir_y = direction.as_xy()
            if (dir_x, dir_y) == (dx, dy):
                return direction

        return None


    def count_known_free_neighbors(self, position):
        x, y = position
        count = 0

        for direction in D:
            dx, dy = direction.as_xy()
            nx = x + dx
            ny = y + dy

            if self.is_known_free(nx, ny):
                count += 1

        return count


    def is_enemy_danger_zone(self, position):
        for enemy_position in self.current_enemies:
            enemy_x, enemy_y = enemy_position

            distance = max(
                abs(position[0] - enemy_x),
                abs(position[1] - enemy_y)
            )

            if distance <= 1:
                return True

        return False



# ============================================================
# Pathfinding and movement conversion
# ============================================================

    def shortest_path(self, start, goal):
        """
        Find the shortest known path with BFS.
        Intermediate fields must be known empty; the gold goal may be entered
        as long as it is not a known wall.
        """
        queue = deque([start])
        came_from = {start: None}

        while queue:
            current_x, current_y = queue.popleft()

            if (current_x, current_y) == goal:
                break

            for direction in D:
                dx, dy = direction.as_xy()
                next_x = current_x + dx
                next_y = current_y + dy
                next_pos = (next_x, next_y)

                if next_pos in self.current_enemies and next_pos != goal:
                    continue

                if next_pos in came_from:
                    continue

                if next_pos == goal:
                    if not self.in_bounds(next_x, next_y):
                        continue
                    if self.ourMap[next_x, next_y].status == TileStatus.Wall:
                        continue
                else:
                    if not self.is_known_free(next_x, next_y):
                        continue

                came_from[next_pos] = (current_x, current_y)
                queue.append(next_pos)

        if goal not in came_from:
            return None

        path = []
        current = goal

        while current is not None:
            path.append(current)
            current = came_from[current]

        path.reverse()
        return path


    def path_to_moves(self, path, max_moves, allow_risky_first_step=False):
        # Convert the next coordinates of a planned path into actual movement directions.
        moves = []

        for i in range(1, min(len(path), max_moves + 1)):
            start_x, start_y = path[i - 1]
            next_x, next_y = path[i]
            next_position = (next_x, next_y)

            # Avoid risky first-step collisions, except when we explicitly allow risk.
            if (
                i == 1
                and not allow_risky_first_step
                and self.is_enemy_danger_zone(next_position)
            ):
                break

            direction = self.direction_from_to(start_x, start_y, next_x, next_y)

            if direction is None:
                break

            moves.append(direction)

        return moves

    def move_cost(self, number_of_moves):
        return number_of_moves * (number_of_moves + 1) // 2



# ============================================================
# Enemy tracking and score estimation
# ============================================================

    def update_enemy_tracker(self, status):
        for other in status.others:
            if other is None:
                continue

            enemy_id = other.player
            current_position = (other.x, other.y)

            if enemy_id in self.enemy_history:
                last_position = self.enemy_history[enemy_id]["last_position"]

                distance_moved = max(
                    abs(current_position[0] - last_position[0]),
                    abs(current_position[1] - last_position[1])
                )

                if distance_moved <= 6:
                    old_average = self.enemy_history[enemy_id]["average_speed"]
                    new_average = 0.5 * old_average + 0.5 * distance_moved
                    self.enemy_history[enemy_id]["average_speed"] = new_average

                self.enemy_history[enemy_id]["last_position"] = current_position

            else:
                self.enemy_history[enemy_id] = {
                    "last_position": current_position,
                    "average_speed": self.DEFAULT_ENEMY_SPEED
                }


    def update_shadow_scoreboard(self, status):
        """
        Very rough score estimate for visible opponents.
        This is copied conceptually from RivalrySprint:
        if a known pot disappears and an opponent is close to its old location,
        we assume that opponent collected it.
        """
        if self.last_pots:
            for location, amount in self.last_pots.items():
                if not status.goldPots or location not in status.goldPots:
                    grabbed_by = None

                    for other in status.others:
                        if other is None:
                            continue

                        distance_to_old_pot = max(
                            abs(other.x - location[0]),
                            abs(other.y - location[1])
                        )

                        if distance_to_old_pot <= self.LOST_POT_ENEMY_DISTANCE:
                            grabbed_by = other.player
                            break

                    if grabbed_by is not None:
                        self.estimated_scores[grabbed_by] += amount

        self.estimated_scores[self.player_id] = status.gold
        self.last_pots = status.goldPots.copy() if status.goldPots else {}


    def is_rivalry_mode(self, current_gold):
        rival_score = -1

        for player_id, estimated_score in self.estimated_scores.items():
            if player_id == self.player_id:
                continue

            if estimated_score > rival_score:
                rival_score = estimated_score

        return rival_score > current_gold + self.RIVALRY_SCORE_MARGIN



# ============================================================
# Gold chasing and sprint decisions
# ============================================================


    def is_gold_path_reasonable(self, position, gold_position, path):
        # Accept a known gold path only if it is not an excessive detour.

        path_length = len(path) - 1

        direct_distance = max(
            abs(gold_position[0] - position[0]),
            abs(gold_position[1] - position[1])
        )

        return path_length <= direct_distance * self.GOLD_PATH_FACTOR + self.GOLD_PATH_BONUS


    def choose_burst_length(self, path_length, gold_value, current_gold):
        # Decide how many moves to buy without spending too much gold for the current pot.
        burst_length = 1

        for number_of_moves in range(1, min(path_length, self.MAX_BURST_MOVES) + 1):
            cost = self.move_cost(number_of_moves)

            if cost > current_gold - self.MINIMUM_GOLD_RESERVE:
                break

            if cost > gold_value * self.GOLD_SPEND_FRACTION:
                break

            burst_length = number_of_moves

        return burst_length


    def get_enemy_paths_to_gold(self, status, gold_position):
        enemy_paths = []

        for other in status.others:
            if other is None:
                continue

            enemy_position = (other.x, other.y)
            enemy_path = self.shortest_path(enemy_position, gold_position)

            if enemy_path is not None and len(enemy_path) > 1:
                enemy_paths.append((other.player, enemy_path))

        return enemy_paths
    

    def calculate_sprint_decision(self, path_to_gold, enemy_paths, current_gold, gold_value, rivalry_mode):
        """
        RivalrySprint-style decision:
        - estimate whether an enemy may arrive earlier
        - if yes, check whether a sprint can still beat them
        - only sprint if the pot value justifies the movement cost
        - if no enemy is faster, use a normal controlled burst
        """
        distance_to_gold = len(path_to_gold) - 1

        if distance_to_gold <= 0:
            return True, 0

        fastest_enemy_eta = float("inf")
        closest_enemy_distance = float("inf")

        for enemy_id, enemy_path in enemy_paths:
            enemy_distance = len(enemy_path) - 1
            enemy_speed = self.enemy_history.get(
                enemy_id,
                {"average_speed": self.DEFAULT_ENEMY_SPEED}
            )["average_speed"]

            enemy_eta = enemy_distance / max(0.1, enemy_speed)

            fastest_enemy_eta = min(fastest_enemy_eta, enemy_eta)
            closest_enemy_distance = min(closest_enemy_distance, enemy_distance)


        # If an enemy can take the pot immediately and is closer than we are,
        # do not waste a big sprint.
        if fastest_enemy_eta <= 1.0 and closest_enemy_distance <= distance_to_gold:
            return False, 0

        our_normal_eta = distance_to_gold / 2.0

        if fastest_enemy_eta <= our_normal_eta:
            target_eta = max(1.0, fastest_enemy_eta - 1.0)
            desired_moves = math.ceil(distance_to_gold / target_eta)
            desired_moves = min(desired_moves, distance_to_gold)

            sprint_cost = self.move_cost(desired_moves)
            expected_profit = gold_value - sprint_cost
            min_profit = self.MIN_PROFIT_RIVALRY if rivalry_mode else self.MIN_PROFIT_NORMAL

            if sprint_cost <= current_gold and expected_profit >= min_profit:
                return True, desired_moves

            return False, 0

        # If nobody seems faster, use a controlled but more RivalrySprint-like burst.
        if current_gold > self.HIGH_BUDGET_THRESHOLD and distance_to_gold <= self.MAX_BURST_MOVES:
            return True, distance_to_gold

        if current_gold > self.HIGH_BUDGET_THRESHOLD:
            return True, min(self.HIGH_BUDGET_BURST, distance_to_gold)

        return True, min(2, distance_to_gold)



# ============================================================
# Exploration and fallback positioning
# ============================================================


    def find_frontiers(self):
    # Find known empty fields that border unknown areas and are useful for exploration.
        frontiers = []

        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if self.ourMap[x, y].status != TileStatus.Empty:
                    continue

                for direction in D:
                    dx, dy = direction.as_xy()
                    neighbor_x = x + dx
                    neighbor_y = y + dy

                    if not self.in_bounds(neighbor_x, neighbor_y):
                        continue

                    if self.ourMap[neighbor_x, neighbor_y].status == TileStatus.Unknown:
                        frontiers.append((x, y))
                        break

        return frontiers

    
    def choose_best_frontier(self, position, gold_position):
        # Choose the reachable frontier that is close to us and still roughly points toward the gold.
        frontiers = self.find_frontiers()

        best_path = None
        best_score = float("inf")

        for frontier in frontiers:
            path = self.shortest_path(position, frontier)

            if path is None or len(path) < 2:
                continue

            distance_to_frontier = len(path) - 1
            distance_to_gold = max(
                abs(gold_position[0] - frontier[0]),
                abs(gold_position[1] - frontier[1])
            )


            # The score prefers nearby frontiers, but adds a smaller penalty for being far from the gold.
            # This makes exploration still move roughly toward the current gold instead of wandering randomly.
            score = distance_to_frontier + self.FRONTIER_GOLD_WEIGHT * distance_to_gold

            if score < best_score:
                best_score = score
                best_path = path

        return best_path


    def choose_spawn_positioning_path(self, current_position, gold_position):
        """
        Choose a positioning target for the next gold spawn.

        Idea:
        If the current gold is probably lost, most bots will cluster near it.
        We move toward a position around the map center, slightly away from the
        current gold. This should keep us flexible for the next gold spawn.
        """
        center_x = self.ourMap.width // 2
        center_y = self.ourMap.height // 2

        gold_x, gold_y = gold_position

        # Vector from gold to center
        away_x = center_x - gold_x
        away_y = center_y - gold_y

        # Target: center, shifted a bit away from the current gold.
        target_x = round(center_x + 0.5 * away_x)
        target_y = round(center_y + 0.5 * away_y)

        # Keep target inside the map.
        target_x = max(0, min(self.ourMap.width - 1, target_x))
        target_y = max(0, min(self.ourMap.height - 1, target_y))

        target = (target_x, target_y)

        best_candidate = None
        best_score = float("inf")

        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                candidate = (x, y)

                if not self.is_known_free(x, y):
                    continue

                if candidate in self.current_enemies:
                    continue

                # Approximate distance to our desired spawn-positioning target.
                distance_to_target = max(
                    abs(candidate[0] - target[0]),
                    abs(candidate[1] - target[1])
                )

                # Prefer candidates that are not too far from us.
                distance_from_us = max(
                    abs(candidate[0] - current_position[0]),
                    abs(candidate[1] - current_position[1])
                )

                # Prefer more open fields a little bit.
                free_neighbors = self.count_known_free_neighbors(candidate)

                score = (
                    distance_to_target
                    + 0.4 * distance_from_us
                    - 1.0 * free_neighbors
                )

                if score < best_score:
                    best_score = score
                    best_candidate = candidate

        if best_candidate is None:
            return None

        return self.shortest_path(current_position, best_candidate)



    def teammate_is_better_for_gold(self, current_position, gold_position, margin=3):
        """
        Return True if S5 has a clearly shorter known path to the current gold.
        This is used so S3_1 can avoid chasing a pot that S5 is much more likely to reach.
        """
        s5_position = TEAM_POSITIONS.get("S5")

        if s5_position is None:
            return False

        my_path = self.shortest_path(current_position, gold_position)
        s5_path = self.shortest_path(s5_position, gold_position)

        if my_path is None or s5_path is None:
            return False

        my_distance = len(my_path) - 1
        s5_distance = len(s5_path) - 1

        return s5_distance + margin < my_distance



    def move(self, status):
        self.update_shadow_scoreboard(status)

        if not status.goldPots:
            return []

        # Update remembered map with all currently visible fields
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if status.map[x, y].status != TileStatus.Unknown:
                    self.ourMap[x, y].status = status.map[x, y].status
        # Update internal map with all currently visible fields.
        # Unknown fields are ignored, so previously discovered information is not overwritten.
        
        # Share this bot's visible map with the team and import teammate knowledge
        share_visible_map(status)
        import_team_map(self)


        # If health is too low, do not move
        if status.health < 30:
            return []

        # Get current position and nearest known gold pot
        current_position = (status.x, status.y)
        gold_position = next(iter(status.goldPots))

        TEAM_POSITIONS["S3_1"] = current_position

        if status.gold < 10:
            distance_to_gold = max(
                abs(gold_position[0] - current_position[0]),
                abs(gold_position[1] - current_position[1])
            )

            if distance_to_gold > 1:
                return []

        self.current_enemies = set()

        for other in status.others:
            if other is not None:
                self.current_enemies.add((other.x, other.y))

        self.update_enemy_tracker(status)

        # Try to find a shortest path to the gold using our remembered map
        path_to_gold = self.shortest_path(current_position, gold_position)

        s5_is_better_for_gold = self.teammate_is_better_for_gold(
            current_position,
            gold_position,
            margin=TEAM_GOLD_MARGIN
        )
        
        if (
            not s5_is_better_for_gold
            and path_to_gold is not None
            and len(path_to_gold) > 1
            and self.is_gold_path_reasonable(current_position, gold_position, path_to_gold)
        ):
            path_length = len(path_to_gold) - 1
            gold_value = status.goldPots[gold_position]

            enemy_paths = self.get_enemy_paths_to_gold(status, gold_position)
            rivalry_mode = self.is_rivalry_mode(status.gold)

            chasing_gold, burst_length = self.calculate_sprint_decision(
                path_to_gold,
                enemy_paths,
                status.gold,
                gold_value,
                rivalry_mode
            )

            if chasing_gold and burst_length > 0:
                allow_risky_first_step = path_length <= 3 and burst_length >= path_length

                moves = self.path_to_moves(
                    path_to_gold,
                    burst_length,
                    allow_risky_first_step=allow_risky_first_step
                )

                if moves:
                    return moves

            # Only if the sprint calculation says the race is not worth it,
            # position for the next gold spawn.
            path_to_spawn_position = self.choose_spawn_positioning_path(
                current_position,
                gold_position
            )

            if path_to_spawn_position is not None and len(path_to_spawn_position) > 1:
                moves = self.path_to_moves(path_to_spawn_position, 1)

                if moves:
                    return moves

        # If no known path to the gold was found, explore a reachable frontier
        path_to_frontier = self.choose_best_frontier(current_position, gold_position)

        if path_to_frontier is not None and len(path_to_frontier) > 1:
            next_x, next_y = path_to_frontier[1]
            direction = self.direction_from_to(status.x, status.y, next_x, next_y)

            if direction is not None:
                return [direction]

        # If neither gold nor frontier is reachable, stay in place
        return []


# Allow optimization_runner_S3_1.py to override selected class parameters without
# editing this bot file for every test run.
TUNABLE_PARAMETERS = [
    "MAX_BURST_MOVES",
    "GOLD_SPEND_FRACTION",
    "MINIMUM_GOLD_RESERVE",
    "DEFAULT_ENEMY_SPEED",
    "HIGH_BUDGET_THRESHOLD",
    "HIGH_BUDGET_BURST",
    "MIN_PROFIT_NORMAL",
    "MIN_PROFIT_RIVALRY",
    "FRONTIER_GOLD_WEIGHT",
    "GOLD_PATH_FACTOR",
    "GOLD_PATH_BONUS",
    "RIVALRY_SCORE_MARGIN",
    "LOST_POT_ENEMY_DISTANCE",
]

if bot_params is not None:
    for parameter_name in TUNABLE_PARAMETERS:
        if hasattr(bot_params, parameter_name):
            setattr(StrategyThreeOneBot, parameter_name, getattr(bot_params, parameter_name))


# ============================================================
# Current best confirmed parameters
# ============================================================
# S5 placeholder uses our best S5 config #11.
StrategyFiveBot.MAX_BURST_MOVES = 4
StrategyFiveBot.GOLD_SPEND_FRACTION = 0.25
StrategyFiveBot.MINIMUM_GOLD_RESERVE = 10
StrategyFiveBot.GOLD_PATH_FACTOR = 2.5
StrategyFiveBot.GOLD_PATH_BONUS = 8
StrategyFiveBot.DISTANCE_CUTOFF = 0.90
StrategyFiveBot.LOW_GOLD_RECOVERY_THRESHOLD = 10
StrategyFiveBot.UNWINNABLE_ETA_RATIO = 0.7
StrategyFiveBot.LOSING_STREAK_THRESHOLD = 5
StrategyFiveBot.STRATEGY_PATIENCE = 6
StrategyFiveBot.RIVALRY_SCORE_MARGIN = 500
StrategyFiveBot.STATIONARY_SPAWN_BLOCK_RADIUS = 4
StrategyFiveBot.STATIONARY_SPAWN_BLOCK_PENALTY = 4.0

# S3_1 uses current best confirmed config #8.
StrategyThreeOneBot.MAX_BURST_MOVES = 5
StrategyThreeOneBot.GOLD_SPEND_FRACTION = 0.30
StrategyThreeOneBot.MINIMUM_GOLD_RESERVE = 30
StrategyThreeOneBot.GOLD_PATH_FACTOR = 2.0
StrategyThreeOneBot.GOLD_PATH_BONUS = 3
StrategyThreeOneBot.FRONTIER_GOLD_WEIGHT = 0.8
StrategyThreeOneBot.HIGH_BUDGET_THRESHOLD = 80
StrategyThreeOneBot.HIGH_BUDGET_BURST = 3
StrategyThreeOneBot.DEFAULT_ENEMY_SPEED = 2.0
StrategyThreeOneBot.LOST_POT_ENEMY_DISTANCE = 2
StrategyThreeOneBot.MIN_PROFIT_NORMAL = 1
StrategyThreeOneBot.MIN_PROFIT_RIVALRY = 0
StrategyThreeOneBot.RIVALRY_SCORE_MARGIN = 25


# The simulator imports this list. Because there are two objects here,
# the game loads and visualizes them as two separate players.
players = [
    StrategyFiveBot(),
    StrategyThreeOneBot(),
]
