from game_utils import Direction as D 
from game_utils import Map, TileStatus 
from player_base import Player
from collections import deque
import math
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
        
        # If health is too low, do not move
        if status.health < 30:
            return []

        # Get current position and nearest known gold pot
        current_position = (status.x, status.y)
        gold_position = next(iter(status.goldPots))

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

        if (
            path_to_gold is not None
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

players = [StrategyThreeOneBot()]
# The simulator imports this list to load our bot.