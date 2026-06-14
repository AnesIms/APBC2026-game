# XAE-12-Team.py
# Final team file: StalkerHunter + optimized S3_1.
# Both bots share discovered map fields. S3_1 only gives up a pot
# when StalkerHunter is clearly closer to it.

from game_utils import Direction as D, Map, TileStatus
from player_base import Player
from collections import deque
import math


TEAM_GOLD_MARGIN = 7
TEAM_MAP = None
TEAM_POSITIONS = {}


def ensure_team_map(width, height):
    global TEAM_MAP
    if TEAM_MAP is None:
        TEAM_MAP = Map(width, height)
    return TEAM_MAP


def share_visible_map(status):
    # Add currently visible tiles to the shared team map.
    team_map = ensure_team_map(status.map.width, status.map.height)

    for x in range(team_map.width):
        for y in range(team_map.height):
            if status.map[x, y].status != TileStatus.Unknown:
                team_map[x, y].status = status.map[x, y].status


def import_team_map(bot):
    # Copy team knowledge into this bot's own map.
    if TEAM_MAP is None:
        return

    for x in range(TEAM_MAP.width):
        for y in range(TEAM_MAP.height):
            if TEAM_MAP[x, y].status != TileStatus.Unknown:
                bot.ourMap[x, y].status = TEAM_MAP[x, y].status


class StalkerHunterPlayer(Player):

    # ---- Movement & Speed ----
    DEFAULT_WALK_SPEED = 3.0
    DEFAULT_SPRINT_SPEED = 7.0
    DEFAULT_SPRINT_RANGE = 7.0
    DEFAULT_AVERAGE_SPEED = 3.0

    # ---- Economy & Profit Margins ----
    MIN_PROFIT_NORMAL = 10
    MIN_PROFIT_RIVALRY = 0
    MAX_ATTRIBUTED_COST_DIST = 7

    # ---- Pathing & Distance Checks ----
    GOLD_PATH_FACTOR = 2.0
    GOLD_PATH_BONUS = 5
    ENEMY_DISTANCE_CUTOFF = 2

    # ---- Sprint Action Moves ----
    NORMAL_BUDGET_DEFAULT_MOVES = 3
    RIVALRY_ETA_SAFETY_MARGIN = 1.0

    # ---- Strategy Triggers & Escalation ----
    LOSING_RANK_THRESHOLD = 2
    LOSING_STREAK_THRESHOLD = 2
    STRATEGY_PATIENCE = 4
    BLIND_CHASER_MAX_ROUNDS = 350
    RANK_DROP_CAMPING_TRIGGER = 2
    RIVALRY_SCORE_MARGIN = 100
    RIVALRY_MAX_RANK = 1

    # ---- Recovery Mode ----
    RECOVERY_LOW_THRESHOLD = 30
    RECOVERY_HIGH_THRESHOLD = 50

    # ---- Camping & Stalking Behavior ----
    STALK_DISTANCE = 1
    MAX_STALK_MOVES = 3

    # ---- Fallback & Positioning Weights ----
    FALLBACK_CURRENT_POS_WEIGHT = 0.4
    FALLBACK_FREE_NEIGHBOR_WEIGHT = 1.0
    FRONTIER_GOLD_DIST_WEIGHT = 0.5
    FALLBACK_MOVES = 2

    # ---- Tracking & Health ----
    LOW_HEALTH_THRESHOLD = 30
    LEADER_HISTORY_MAX_AGE = 200
    STALENESS_PENALTY_WEIGHT = 0.5

    def reset(self, player_id, max_players, width, height):
        self.player_name = "StalkerHunter"
        self.ourMap = Map(width, height)
        ensure_team_map(width, height)
        self.current_enemies = set()
        self.enemy_history = {}
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
        self.pre_recovery_strategy = None
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

    def round_begin(self, r):
        self.current_round = r
        if self.active_strategy == "blind_chaser":
            self.blind_chaser_rounds += 1

    def set_mines(self, status):
        return []

    # ---- Map helpers ----

    def in_bounds(self, x, y):
        return 0 <= x < self.ourMap.width and 0 <= y < self.ourMap.height

    def is_known_free(self, x, y):
        if not self.in_bounds(x, y):
            return False
        return self.ourMap[x, y].status == TileStatus.Empty

    def direction_from_to(self, start_x, start_y, target_x, target_y):
        dx, dy = target_x - start_x, target_y - start_y
        for direction in D:
            dir_x, dir_y = direction.as_xy()
            if (dir_x, dir_y) == (dx, dy):
                return direction
        return None

    def count_known_free_neighbors(self, position):
        x, y = position
        return sum(
            1 for d in D
            if self.is_known_free(x + d.as_xy()[0], y + d.as_xy()[1])
        )

    # ---- Pathfinding ----

    def shortest_path(self, start, goal):
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
        paths = []
        for other in status.others:
            if other is None:
                continue
            p = self.shortest_path((other.x, other.y), target)
            if p and len(p) > 1:
                paths.append((other.player, p))
        return paths

    def safe_path_to_moves(self, path, max_moves, enemy_paths):
        moves = []
        path_to_walk = path[1:]
        current_node = path[0]

        for i in range(min(max_moves, len(path_to_walk))):
            next_node = path_to_walk[i]
            my_arrival_time = i + 1

            contested = any(
                next_node in e_path and e_path.index(next_node) < my_arrival_time
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
        for other in status.others:
            if other is None:
                continue
            enemy_id = other.player
            current_position = (other.x, other.y)

            if enemy_id not in self.enemy_history:
                self.enemy_history[enemy_id] = {
                    "last_position": current_position,
                    "sprint_speed": self.DEFAULT_SPRINT_SPEED,
                    "walk_speed": self.DEFAULT_WALK_SPEED,
                    "max_sprint_rounds": 1,
                    "current_sprint_streak": 0,
                    "last_seen_round": self.current_round,
                    "total_distance": 0.0,
                    "total_rounds_seen": 0,
                    "average_speed": self.DEFAULT_AVERAGE_SPEED,
                }
            else:
                hist = self.enemy_history[enemy_id]
                last_position = hist["last_position"]
                distance_moved = max(
                    abs(current_position[0] - last_position[0]),
                    abs(current_position[1] - last_position[1]),
                )

                if self.current_round - hist["last_seen_round"] == 1:
                    hist["total_distance"] += distance_moved
                    hist["total_rounds_seen"] += 1
                    hist["average_speed"] = hist["total_distance"] / hist["total_rounds_seen"]

                    if distance_moved > self.DEFAULT_WALK_SPEED:
                        hist["sprint_speed"] = max(hist["sprint_speed"], distance_moved)
                        hist["current_sprint_streak"] += 1
                        hist["max_sprint_rounds"] = max(hist["max_sprint_rounds"], hist["current_sprint_streak"])
                    elif distance_moved > 0:
                        hist["walk_speed"] = max(hist["walk_speed"], distance_moved)
                        hist["current_sprint_streak"] = 0
                else:
                    hist["current_sprint_streak"] = 0

                hist["last_position"] = current_position
                hist["last_seen_round"] = self.current_round

    def calculate_enemy_eta_burst(self, enemy_id, enemy_distance):
        hist = self.enemy_history.get(enemy_id, {})
        sprint_speed = hist.get("sprint_speed", self.DEFAULT_SPRINT_SPEED)
        walk_speed = hist.get("walk_speed", self.DEFAULT_WALK_SPEED)
        max_sprint_rounds = hist.get("max_sprint_rounds", 1)

        max_sprint_distance = sprint_speed * max_sprint_rounds
        if enemy_distance <= max_sprint_distance:
            return enemy_distance / max(1, sprint_speed)

        walk_dist = enemy_distance - max_sprint_distance
        return (max_sprint_distance / max(1, sprint_speed)) + (walk_dist / max(1, walk_speed))

    def calculate_enemy_eta_average(self, enemy_id, enemy_distance):
        hist = self.enemy_history.get(enemy_id, {})
        avg_speed = hist.get("average_speed", self.DEFAULT_AVERAGE_SPEED)
        return enemy_distance / max(1.0, avg_speed)

    # ---- Score estimation ----

    def _attribute_pot(self, pot_pos, pot_value, status):
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

            eta = self.calculate_enemy_eta_average(pid, dist) + staleness * self.STALENESS_PENALTY_WEIGHT
            cost = status.params.cost(min(dist, self.MAX_ATTRIBUTED_COST_DIST))
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
        sorted_scores = sorted(self.estimated_scores.items(), key=lambda x: x[1], reverse=True)
        for i, (pid, _) in enumerate(sorted_scores):
            if pid == self.player_id:
                return i + 1
        return self.max_players

    def is_forced_rivalry(self, current_gold):
        return (self.get_my_rank() <= self.RIVALRY_MAX_RANK and
                self.leader_score - current_gold > self.RIVALRY_SCORE_MARGIN)

    # ---- Strategy state machine ----

    def _set_strategy(self, new_strategy):
        if self.active_strategy != new_strategy:
            self.active_strategy = new_strategy

    def _enter_recovery(self):
        if self.active_strategy != "recovery":
            self.pre_recovery_strategy = self.active_strategy
            self._set_strategy("recovery")

    def _exit_recovery(self):
        resume = self.pre_recovery_strategy or "blind_chaser"
        if resume == "blind_chaser":
            resume = "camping"
        self.pre_recovery_strategy = None
        self._set_strategy(resume)
        self.last_round_rank = self.get_my_rank()
        self.losing_streak = 0
        self.blind_chaser_rounds = 0
        self.camping_pots_played = 0
        self.camping_rank_sum = 0

    def _on_new_pot(self, new_gold_pos, current_score, pot_is_unwinnable=False):
        current_rank = self.get_my_rank()

        if self.pot_gold_id is not None:
            score_gained = current_score - self.pot_score_at_spawn
            won_pot = score_gained > 0

            if not self.pot_was_unwinnable and self.active_strategy != "recovery":
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
        for enemy_id, enemy_path in enemy_paths:
            enemy_dist = len(enemy_path) - 1
            if enemy_dist <= self.ENEMY_DISTANCE_CUTOFF and enemy_dist < our_dist:
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

    def calculate_sprint_decision_simple(self, path_to_gold, enemy_paths, current_gold, gold_value, params):
        distance_to_gold = len(path_to_gold) - 1
        if distance_to_gold <= 0:
            return True, 0
        closest_enemy_distance = min(
            (len(ep) - 1 for _, ep in enemy_paths),
            default=float("inf")
        )
        if closest_enemy_distance <= self.ENEMY_DISTANCE_CUTOFF and closest_enemy_distance < distance_to_gold:
            return False, 0

        full_sprint_cost = params.cost(distance_to_gold)
        if full_sprint_cost <= current_gold and (gold_value - full_sprint_cost) > self.MIN_PROFIT_NORMAL:
            return True, distance_to_gold
        return True, min(self.NORMAL_BUDGET_DEFAULT_MOVES, distance_to_gold)

    def calculate_sprint_decision(self, path_to_gold, enemy_paths, current_gold, gold_value, rivalry_mode, params):
        distance_to_gold = len(path_to_gold) - 1
        if distance_to_gold <= 0:
            return True, 0

        fastest_enemy_eta = float('inf')
        closest_enemy_distance = float('inf')

        for enemy_id, enemy_path in enemy_paths:
            enemy_distance = len(enemy_path) - 1
            if rivalry_mode:
                enemy_eta = self.calculate_enemy_eta_average(enemy_id, enemy_distance)
            else:
                enemy_eta = self.calculate_enemy_eta_burst(enemy_id, enemy_distance)
            if enemy_eta < fastest_enemy_eta:
                fastest_enemy_eta = enemy_eta
            if enemy_distance < closest_enemy_distance:
                closest_enemy_distance = enemy_distance

        if not rivalry_mode:
            if closest_enemy_distance <= self.ENEMY_DISTANCE_CUTOFF and closest_enemy_distance < distance_to_gold:
                return False, 0

        our_normal_eta = distance_to_gold / self.DEFAULT_WALK_SPEED

        if fastest_enemy_eta <= our_normal_eta:
            target_eta = max(1.0, fastest_enemy_eta - self.RIVALRY_ETA_SAFETY_MARGIN)
            desired_moves = min(math.ceil(distance_to_gold / target_eta), distance_to_gold)
            sprint_cost = params.cost(desired_moves)
            eta_rounds = math.ceil(distance_to_gold / max(1, desired_moves))
            decay_penalty = eta_rounds * params.goldPerRound if params.goldDecrease else 0
            expected_profit = (gold_value - decay_penalty) - sprint_cost

            min_profit = self.MIN_PROFIT_RIVALRY if rivalry_mode else self.MIN_PROFIT_NORMAL
            if expected_profit >= min_profit and sprint_cost <= current_gold:
                return True, desired_moves
            return False, 0

        full_sprint_cost = params.cost(distance_to_gold)
        min_profit = self.MIN_PROFIT_RIVALRY if rivalry_mode else self.MIN_PROFIT_NORMAL
        if (distance_to_gold <= self.DEFAULT_SPRINT_RANGE
                and full_sprint_cost <= current_gold
                and (gold_value - full_sprint_cost) >= min_profit):
            return True, distance_to_gold

        return True, min(self.NORMAL_BUDGET_DEFAULT_MOVES, distance_to_gold)

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
            enemy_sprint_speed = self.enemy_history.get(other.player, {}).get("sprint_speed", self.DEFAULT_SPRINT_SPEED)
            if enemy_dist <= enemy_sprint_speed:
                return False
            if self.calculate_enemy_eta_burst(other.player, enemy_dist) <= my_eta:
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
            enemy_sprint_speed = self.enemy_history.get(other.player, {}).get("sprint_speed", self.DEFAULT_SPRINT_SPEED)
            if (enemy_dist <= enemy_sprint_speed and
                    self.estimated_scores.get(other.player, 100) >= status.params.cost(enemy_dist)):
                return True
        return False

    # ---- Fallback positioning ----

    def get_fallback_path(self, current_pos):
        target = self.center
        if target in self.current_enemies:
            best_candidate = None
            best_dist = float('inf')
            for x in range(self.ourMap.width):
                for y in range(self.ourMap.height):
                    if (x, y) in self.current_enemies or self.ourMap[x, y].status == TileStatus.Wall:
                        continue
                    dist = max(abs(x - self.center[0]), abs(y - self.center[1]))
                    if dist < best_dist:
                        best_dist = dist
                        best_candidate = (x, y)
            if best_candidate:
                target = best_candidate
        return self.shortest_path(current_pos, target)

    def get_predictive_fallback_path(self, current_pos, gold_pos):
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
                score = (
                    max(abs(x - target[0]), abs(y - target[1]))
                    + self.FALLBACK_CURRENT_POS_WEIGHT * max(abs(x - current_pos[0]), abs(y - current_pos[1]))
                    - self.FALLBACK_FREE_NEIGHBOR_WEIGHT * self.count_known_free_neighbors((x, y))
                )
                if score < best_score:
                    best_score = score
                    best_candidate = (x, y)

        return self.shortest_path(current_pos, best_candidate) if best_candidate else None

    def get_best_frontier_target(self, pos, gold_pos):
        frontiers = []
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if self.ourMap[x, y].status != TileStatus.Empty or (x, y) in self.current_enemies:
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
            score = (len(path) - 1 + self.FRONTIER_GOLD_DIST_WEIGHT * dist_to_gold, frontier[0], frontier[1])
            if score < best_score:
                best_score = score
                best_path = path

        return best_path

    # ---- Main orchestrator ----

    def move(self, status):
        self.update_shadow_scoreboard(status)
        if not status.goldPots:
            return []

        current_gold_pos = min(
            status.goldPots.keys(),
            key=lambda p: max(abs(status.x - p[0]), abs(status.y - p[1]))
        )

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

        share_visible_map(status)
        import_team_map(self)

        if status.health < self.LOW_HEALTH_THRESHOLD:
            return []

        current_pos = (status.x, status.y)
        gold_pos = current_gold_pos
        TEAM_POSITIONS["StalkerHunter"] = current_pos

        self.current_enemies = set()
        for other in status.others:
            if other is not None:
                self.current_enemies.add((other.x, other.y))

        self.update_enemy_tracker(status, gold_pos)

        if self.active_strategy != "recovery" and status.gold < self.RECOVERY_LOW_THRESHOLD:
            self._enter_recovery()
        elif self.active_strategy == "recovery" and status.gold >= self.RECOVERY_HIGH_THRESHOLD:
            self._exit_recovery()

        effective_strategy = self.active_strategy
        if effective_strategy == "camping" and self.is_forced_rivalry(status.gold):
            effective_strategy = "rivalry"

        current_rank = self.get_my_rank()

        if (self.active_strategy == "blind_chaser"
                and self.blind_chaser_rounds >= self.BLIND_CHASER_MAX_ROUNDS
                and current_rank > 1):
            self._set_strategy("rivalry")
            effective_strategy = "rivalry"
            self.losing_streak = 0
            self.camping_pots_played = 0
            self.camping_rank_sum = 0
        elif (self.active_strategy == "blind_chaser"
                and self.last_round_rank is not None
                and current_rank - self.last_round_rank >= self.RANK_DROP_CAMPING_TRIGGER):
            self._set_strategy("camping")
            effective_strategy = "camping"
            self.losing_streak = 0
            self.camping_pots_played = 0
            self.camping_rank_sum = 0

        self.last_round_rank = current_rank

        path_to_gold = self.shortest_path(current_pos, gold_pos)
        distance_to_gold = len(path_to_gold) - 1 if path_to_gold else float('inf')
        enemy_paths = self.get_visible_enemy_paths(status, gold_pos)

        chasing_gold = False
        num_moves = 0
        best_path = [current_pos]

        if path_to_gold and not self.pot_abandoned:
            gold_value = status.goldPots[gold_pos]

            if effective_strategy == "recovery":
                closest_enemy_distance = min(
                    (len(ep) - 1 for _, ep in enemy_paths),
                    default=float("inf")
                )
                if closest_enemy_distance > 2:
                    chasing_gold = True
                    best_path = path_to_gold
                    num_moves = distance_to_gold
                    while num_moves > 0 and status.params.cost(num_moves) > status.gold:
                        num_moves -= 1
                    if distance_to_gold > 0:
                        num_moves = max(1, num_moves)
                    else:
                        num_moves = 0

            elif effective_strategy == "blind_chaser":
                if distance_to_gold / self.DEFAULT_AVERAGE_SPEED <= status.goldPotRemainingRounds:
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
                        num_moves = min(self.MAX_STALK_MOVES, distance_to_gold - self.STALK_DISTANCE)
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
            if effective_strategy == "recovery":
                return []

            if gold_pos != self.last_gold_pos:
                self.fallback_target = None
                self.last_gold_pos = gold_pos

            if self.fallback_target:
                if current_pos == self.fallback_target:
                    self.fallback_target = None
                elif not self.shortest_path(current_pos, self.fallback_target):
                    self.fallback_target = None

            if not self.fallback_target:
                if effective_strategy in ["camping", "rivalry"]:
                    fp = self.get_predictive_fallback_path(current_pos, gold_pos)
                    if fp and len(fp) > 1:
                        self.fallback_target = fp[-1]
                else:
                    fp = self.get_fallback_path(current_pos)
                    if fp and len(fp) > 1:
                        self.fallback_target = fp[-1]

                    if not self.fallback_target and effective_strategy == "blind_chaser":
                        fp = self.get_best_frontier_target(current_pos, gold_pos)
                        if fp and len(fp) > 1:
                            self.fallback_target = fp[-1]

            if self.fallback_target:
                path_to_fallback = self.shortest_path(current_pos, self.fallback_target)
                if path_to_fallback and len(path_to_fallback) > 1:
                    best_path = path_to_fallback
                    num_moves = self.FALLBACK_MOVES

        target_node = best_path[-1] if best_path else current_pos
        collision_enemy_paths = self.get_visible_enemy_paths(status, target_node)
        return self.safe_path_to_moves(best_path, num_moves, collision_enemy_paths)


# Second team bot: optimized S3_1

class StrategyThreeOneBot(Player):
    # Optimized S3_1 parameters.
    MAX_BURST_MOVES = 5
    GOLD_SPEND_FRACTION = 0.30
    MINIMUM_GOLD_RESERVE = 30

    DEFAULT_ENEMY_SPEED = 2.0
    HIGH_BUDGET_THRESHOLD = 80
    HIGH_BUDGET_BURST = 3

    MIN_PROFIT_NORMAL = 1
    MIN_PROFIT_RIVALRY = 0

    FRONTIER_GOLD_WEIGHT = 0.8
    GOLD_PATH_FACTOR = 2.0
    GOLD_PATH_BONUS = 3

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

        # The map starts unknown and is filled while we explore.
    
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


    def teammate_is_better_for_gold(self, current_position, gold_position, margin=TEAM_GOLD_MARGIN):
        teammate_position = TEAM_POSITIONS.get("StalkerHunter")
        if teammate_position is None:
            return False

        my_path = self.shortest_path(current_position, gold_position)
        teammate_path = self.shortest_path(teammate_position, gold_position)
        if my_path is None or teammate_path is None:
            return False

        my_distance = len(my_path) - 1
        teammate_distance = len(teammate_path) - 1
        return teammate_distance + margin < my_distance


    def move(self, status):
        self.update_shadow_scoreboard(status)

        if not status.goldPots:
            return []

        # Add visible fields to our remembered map.
        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                if status.map[x, y].status != TileStatus.Unknown:
                    self.ourMap[x, y].status = status.map[x, y].status

        # Team map: both bots profit from each other's vision.
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
        teammate_is_better_for_gold = self.teammate_is_better_for_gold(
            current_position,
            gold_position,
        )

        if (
            not teammate_is_better_for_gold
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

# The simulator imports this list and starts both team bots.
players = [
    StalkerHunterPlayer(),
    StrategyThreeOneBot(),
]
