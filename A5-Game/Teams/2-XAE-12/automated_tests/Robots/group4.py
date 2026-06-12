#!/usr/bin/env python3

from collections import deque

from Game.game_utils import Direction as D, TileStatus
from Game.game_utils import Map
from Game.player_base import Player


class MyPlayer(Player):

	def reset(self, player_id, max_players, width, height):
		self.player_name = "group4"
		self.player_id = player_id
		self.width = width
		self.height = height
		self.known_map = Map(width, height)

		self.recent_positions = deque(maxlen=12)
		self.position_history = deque(maxlen=8)
		self.gold_history = deque(maxlen=10)
		self.last_opponent_positions = {}
		self.rounds_seen = 0

	def round_begin(self, r):
		pass

	def set_mines(self, status):
		return []

	def update_map(self, status):
		for x in range(self.width):
			for y in range(self.height):
				self.known_map[x, y].obj = None

		for x in range(status.map.width):
			for y in range(status.map.height):
				tile = status.map[x, y]
				if tile.status != TileStatus.Unknown:
					self.known_map[x, y].status = tile.status
					self.known_map[x, y].obj = tile.obj

	def step_pos(self, pos, direction):
		dx, dy = direction.as_xy()
		return pos[0] + dx, pos[1] + dy

	def path_cost(self, steps):
		return steps * (steps + 1) // 2

	def chebyshev(self, a, b):
		return max(abs(a[0] - b[0]), abs(a[1] - b[1]))

	def is_safe_tile(self, x, y, allow_unknown=False):
		if not (0 <= x < self.width and 0 <= y < self.height):
			return False

		tile = self.known_map[x, y]

		if tile.status == TileStatus.Wall:
			return False

		if tile.status == TileStatus.Unknown and not allow_unknown:
			return False

		if tile.obj is not None and tile.obj.is_player():
			return False

		return True

	def breadth_first_search(self, start, goal, danger=None, allow_unknown=True):
		if danger is None:
			danger = set()

		if start == goal:
			return []

		queue = deque([start])
		visited = {start}
		parent = {start: None}
		move_to = {}

		while queue:
			cur = queue.popleft()

			for direction in D:
				nxt = self.step_pos(cur, direction)

				if nxt in visited:
					continue
				if nxt in danger:
					continue
				if not self.is_safe_tile(nxt[0], nxt[1], allow_unknown=allow_unknown):
					continue

				visited.add(nxt)
				parent[nxt] = cur
				move_to[nxt] = direction

				if nxt == goal:
					path = []
					node = nxt
					while parent[node] is not None:
						path.append(move_to[node])
						node = parent[node]
					path.reverse()
					return path

				queue.append(nxt)

		return []

	def max_sprint_length(self, status):
		health_ratio = status.health / 100

		if health_ratio > 0.9:
			health_limit = 7
		elif health_ratio > 0.6:
			health_limit = 5
		elif health_ratio > 0.3:
			health_limit = 3
		else:
			health_limit = 1

		if health_limit >= 7:
			buffer = 30
		elif health_limit >= 5:
			buffer = 15
		elif health_limit >= 3:
			buffer = 10
		else:
			buffer = 5

		gold_limit = 0
		for steps in range(1, 8):
			if self.path_cost(steps) + buffer <= status.gold:
				gold_limit = steps
			else:
				break

		return min(health_limit, gold_limit)

	def profit_margin(self, status):
		if len(self.gold_history) < 4:
			return 10

		growth = self.gold_history[-1] - self.gold_history[0]

		if growth > 20:
			return 1
		elif growth > 5:
			return 10
		elif growth > 0:
			return 20
		else:
			return 5

	def crash_caution_level(self, status):
		health_ratio = status.health / 100
		return 0 if health_ratio > 0.7 else 1

	def predict_danger_tiles(self, status):
		danger = set()
		current_opponent_positions = {}

		all_gold = list(status.goldPots.keys())

		for x in range(self.width):
			for y in range(self.height):
				tile = self.known_map[x, y]

				if tile.obj is None or not tile.obj.is_player():
					continue
				if tile.obj.is_player(self.player_id):
					continue

				opponent_id = tile.obj.as_player()
				opponent_position = (x, y)
				current_opponent_positions[opponent_id] = opponent_position

				predicted = set()

				for gold_x, gold_y in all_gold:
					step_x = 0
					step_y = 0

					if gold_x > x:
						step_x = 1
					elif gold_x < x:
						step_x = -1

					if gold_y > y:
						step_y = 1
					elif gold_y < y:
						step_y = -1

					next_x = x + step_x
					next_y = y + step_y

					if 0 <= next_x < self.width and 0 <= next_y < self.height:
						if self.known_map[next_x, next_y].status != TileStatus.Wall:
							predicted.add((next_x, next_y))

				if not predicted and opponent_id in self.last_opponent_positions:
					last_x, last_y = self.last_opponent_positions[opponent_id]
					move_x = x - last_x
					move_y = y - last_y
					next_x = x + move_x
					next_y = y + move_y

					if 0 <= next_x < self.width and 0 <= next_y < self.height:
						if self.known_map[next_x, next_y].status != TileStatus.Wall:
							predicted.add((next_x, next_y))

				for pos in predicted:
					danger.add(pos)

		self.last_opponent_positions = current_opponent_positions
		return danger

	def should_dodge(self, status):
		me = (status.x, status.y)
		for x in range(self.width):
			for y in range(self.height):
				tile = self.known_map[x, y]
				if tile.obj is None or not tile.obj.is_player():
					continue
				if tile.obj.is_player(self.player_id):
					continue
				if max(abs(x - me[0]), abs(y - me[1])) == 1:
					return True
		return False

	def is_oscillating(self):
		positions = list(self.position_history)
		if len(positions) < 6:
			return False

		if positions[-6:] == [positions[-6], positions[-5], positions[-6], positions[-5], positions[-6], positions[-5]]:
			return True

		if len(positions) >= 6:
			a, b, c = positions[-6], positions[-5], positions[-4]
			if positions[-6:] == [a, b, c, a, b, c]:
				return True

		return False

	def safe_step(self, start, direction, danger):
		nx, ny = self.step_pos(start, direction)
		return (nx, ny) not in danger

	def opponent_pressure(self, status, gold_pos, my_steps):
		best_other = None

		for other in status.others:
			if other is None:
				continue
			other_steps = self.chebyshev((other.x, other.y), gold_pos)
			if best_other is None or other_steps < best_other:
				best_other = other_steps

		if best_other is None:
			return 0

		if best_other < my_steps:
			return 25
		if best_other == my_steps:
			return 12
		if best_other == my_steps + 1:
			return 5
		return 0

	def score_gold_target(self, start, status, gold_pos, amount, path, danger):
		steps = len(path)
		cost = self.path_cost(steps)

		if steps > 0:
			sprint = max(1, self.max_sprint_length(status))
			rounds_needed = -(-steps // sprint)
			if rounds_needed > status.goldPotRemainingRounds:
				return None

		if cost > status.gold:
			return None

		net_gain = amount - cost
		score = 0.0

		score += 3.5 * amount
		score -= 2.0 * cost
		score -= 6.0 * steps
		score -= self.opponent_pressure(status, gold_pos, steps)

		if steps <= 2:
			score += 8

		if net_gain > self.profit_margin(status):
			score += 12
		else:
			score -= 10

		if path and self.safe_step(start, path[0], danger):
			score += 6
		elif path:
			score -= 14

		if self.known_map[gold_pos[0], gold_pos[1]].status != TileStatus.Unknown:
			score += 3

		return score

	def choose_best_gold_target(self, start, status, danger=None):
		if danger is None:
			danger = set()

		best_gold = None
		best_path = None
		best_score = None

		for gold_pos, amount in status.goldPots.items():
			path = self.breadth_first_search(start, gold_pos, danger=danger, allow_unknown=True)

			if not path and gold_pos != start:
				path = self.breadth_first_search(start, gold_pos, danger=set(), allow_unknown=True)

			if not path and gold_pos != start:
				continue

			score = self.score_gold_target(start, status, gold_pos, amount, path, danger)
			if score is None:
				continue

			if best_score is None or score > best_score:
				best_score = score
				best_gold = gold_pos
				best_path = path

		return best_gold, best_path, best_score

	def reposition_step(self, start, status, danger):
		best_direction = None
		best_score = None
		visible_gold = list(status.goldPots.keys())

		for direction in D:
			nx, ny = self.step_pos(start, direction)

			if not self.is_safe_tile(nx, ny, allow_unknown=True):
				continue

			score = 0.0

			if (nx, ny) in danger:
				score -= 20

			if (nx, ny) in self.recent_positions:
				score -= 8

			unseen_count = 0
			for x in range(max(0, nx - 5), min(self.width, nx + 6)):
				for y in range(max(0, ny - 5), min(self.height, ny + 6)):
					if self.known_map[x, y].status == TileStatus.Unknown:
						unseen_count += 1

			score += 0.25 * unseen_count

			center_x = (self.width - 1) / 2
			center_y = (self.height - 1) / 2
			score -= 0.12 * (abs(nx - center_x) + abs(ny - center_y))

			if visible_gold:
				nearest = min(self.chebyshev((nx, ny), gp) for gp in visible_gold)
				avgdist = sum(self.chebyshev((nx, ny), gp) for gp in visible_gold) / len(visible_gold)
				score -= 1.8 * nearest
				score -= 0.7 * avgdist

			if best_score is None or score > best_score:
				best_score = score
				best_direction = direction

		return [best_direction] if best_direction is not None else []

	def move(self, status):
		self.gold_history.append(status.gold)
		self.update_map(status)
		start = (status.x, status.y)

		self.rounds_seen += 1
		self.recent_positions.append(start)
		self.position_history.append(start)

		danger = self.predict_danger_tiles(status)

		if self.crash_caution_level(status) == 0:
			danger = set()

		if self.is_oscillating():
			reposition = self.reposition_step(start, status, danger=set())
			if reposition:
				return reposition

		if self.should_dodge(status) and not status.goldPots:
			for d in D:
				nx, ny = self.step_pos(start, d)
				if (nx, ny) in danger:
					continue
				if not self.is_safe_tile(nx, ny, allow_unknown=True):
					continue
				return [d]

		if status.goldPots:
			gold, path, score = self.choose_best_gold_target(start, status, danger)

			if gold == start:
				return []

			if path:
				steps = len(path)
				gold_amount = status.goldPots[gold]
				max_sprint = max(1, self.max_sprint_length(status))
				sprint_steps = min(steps, max_sprint)
				sprint_cost = self.path_cost(sprint_steps)
				net = gold_amount - sprint_cost

				if (sprint_steps >= 2 and
					net > self.profit_margin(status) + 8 and
					self.safe_step(start, path[0], danger)):
					return path[:sprint_steps]

				if self.safe_step(start, path[0], danger):
					return [path[0]]

				return [path[0]]

		reposition = self.reposition_step(start, status, danger)
		if reposition:
			return reposition

		return []


players = [MyPlayer()]
