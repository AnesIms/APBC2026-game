from game_utils import Direction as D 
from game_utils import Map, TileStatus 
from player_base import Player
from collections import deque
# Import movement directions, map handling, tile information (is the tile a wall, unknown ...), and the base Player class

class StrategyThreeBot(Player):
    # - remember discovered parts of the map
    # - use BFS to find known shortest paths to the gold
    # - explore unknown areas if no useful path to the gold is known
    # - buy multiple moves per round when rushing to gold is worth the cost
    
    def reset(self, player_id, max_players, width, height):
        self.player_name = "XAE-12 S3"
        self.ourMap = Map(width, height)
        self.current_enemies = set()
        self.enemy_history = {}
        # Called once at the beginning of a game.
        # ourMap is our remembered map.
        # It starts mostly unknown, but during the game we continuously update it
        # with all visible fields from the current status.
    
    def round_begin(self, r):
        pass
    # This method is called at the beginning of each round.
    # We currently do not use it, but it could later be useful for
    # round-based strategies, such as detecting gold relocation timing.

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
            score = distance_to_frontier + 0.5 * distance_to_gold

            if score < best_score:
                best_score = score
                best_path = path

        return best_path


    def move_cost(self, number_of_moves):
        return number_of_moves * (number_of_moves + 1) // 2


    def choose_burst_length(self, path_length, gold_value, current_gold):
        # Decide how many moves to buy without spending too much gold for the current pot.
        max_burst_moves = 5
        gold_spend_fraction = 0.25 # Spend max 25% of the current gold pot value
        minimum_gold_reserve = 20

        burst_length = 1

        for number_of_moves in range(1, min(path_length, max_burst_moves) + 1):
            cost = self.move_cost(number_of_moves)

            if cost > current_gold - minimum_gold_reserve:
                break

            if cost > gold_value * gold_spend_fraction:
                break

            burst_length = number_of_moves

        return burst_length


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


    def is_gold_path_reasonable(self, position, gold_position, path):
        # Accept a known gold path only if it is not an excessive detour.

        path_length = len(path) - 1

        direct_distance = max(
            abs(gold_position[0] - position[0]),
            abs(gold_position[1] - position[1])
        )

        return path_length <= direct_distance * 2 + 5


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
                    "average_speed": 2.0
                }


    def estimate_fastest_enemy_eta_to_gold(self, status, gold_position):
        fastest_eta = float("inf")

        for other in status.others:
            if other is None:
                continue

            enemy_id = other.player
            enemy_position = (other.x, other.y)

            path = self.shortest_path(enemy_position, gold_position)

            if path is None:
                continue

            enemy_distance = len(path) - 1
            enemy_speed = self.enemy_history.get(
                enemy_id,
                {"average_speed": 2.0}
            )["average_speed"]

            eta = enemy_distance / max(enemy_speed, 1.0)

            if eta < fastest_eta:
                fastest_eta = eta

        return fastest_eta


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


    def choose_best_hub(self, current_position, gold_position):
        map_center = (self.ourMap.width // 2, self.ourMap.height // 2)

        best_path = None
        best_score = float("inf")

        for x in range(self.ourMap.width):
            for y in range(self.ourMap.height):
                candidate = (x, y)

                if not self.is_known_free(x, y):
                    continue

                if candidate in self.current_enemies:
                    continue

                free_neighbors = self.count_known_free_neighbors(candidate)

                # Only consider useful open junction-like fields.
                if free_neighbors < 4:
                    continue

                approx_distance_from_us = max(
                    abs(candidate[0] - current_position[0]),
                    abs(candidate[1] - current_position[1])
                )

                distance_to_center = max(
                    abs(candidate[0] - map_center[0]),
                    abs(candidate[1] - map_center[1])
                )

                distance_to_gold = max(
                    abs(candidate[0] - gold_position[0]),
                    abs(candidate[1] - gold_position[1])
                )

                score = (
                    approx_distance_from_us
                    + 0.7 * distance_to_center
                    + 0.2 * distance_to_gold
                    - 2.0 * free_neighbors
                )

                if score < best_score:
                    best_score = score
                    best_candidate = candidate

        if best_score == float("inf"):
            return None

        return self.shortest_path(current_position, best_candidate)



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

            enemy_eta = self.estimate_fastest_enemy_eta_to_gold(status, gold_position)
            our_eta = path_length / 2.0

            we_are_likely_first = our_eta <= enemy_eta

            normal_burst = self.choose_burst_length(
                path_length,
                gold_value,
                status.gold
            )

            if our_eta <= enemy_eta:
                # We are probably first: use normal S1 burst.
                burst_length = normal_burst

            elif our_eta <= enemy_eta + 2.5:
                # The race is close: do not give up too early.
                # Move at least 2 steps, but stay within the normal S1 burst limit.
                burst_length = max(2, normal_burst)

            else:
                # Enemy is clearly faster: position for the next gold spawn instead of chasing blindly.
                path_to_spawn_position = self.choose_spawn_positioning_path(
                    current_position,
                    gold_position
                )

                if path_to_spawn_position is not None and len(path_to_spawn_position) > 1:
                    moves = self.path_to_moves(path_to_spawn_position, 1)

                    if moves:
                        return moves

                burst_length = 1

            allow_risky_first_step = path_length <= 3 and burst_length >= path_length

            moves = self.path_to_moves(path_to_gold, burst_length)

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

players = [StrategyThreeBot()]
# The simulator imports this list to load our bot.