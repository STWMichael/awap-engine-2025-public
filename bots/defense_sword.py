from src.player import Player
from src.map import Map
from src.robot_controller import RobotController
from src.game_constants import Team, BuildingType, UnitType, Direction
import math

class BotPlayer(Player):
    def __init__(self, map: Map):
        self.map = map
        # Counter to track consecutive turns without enemy threat.
        # self.noThreatTurns = 0

    def play_turn(self, rc: RobotController):
        team = rc.get_ally_team()
        enemy = rc.get_enemy_team()

        # --- Locate our main castle ---
        main_castle_id = None
        main_castle = None
        for b in rc.get_buildings(team):
            if b.type == BuildingType.MAIN_CASTLE:
                _, main_castle_id = rc.get_id_from_building(b)
                main_castle = b
                break
        if main_castle is None:
            return

        # --- Locate enemy main castle ---
        enemy_castle_id = None
        enemy_castle = None
        for b in rc.get_buildings(enemy):
            if b.type == BuildingType.MAIN_CASTLE:
                _, enemy_castle_id = rc.get_id_from_building(b)
                enemy_castle = b
                break
        if enemy_castle is None:
            return

        turn = rc.get_turn()
        balance = rc.get_balance(team)

        # STEP 1: Clear the spawn tile if necessary.
        self.clear_spawn_tile(rc, main_castle)

        # STEP 2: Gather enemy unit info.
        enemy_units = [rc.get_unit_from_id(uid) for uid in rc.get_unit_ids(enemy) if rc.get_unit_from_id(uid)]
        # If there are no enemy units, increment our no-threat counter; otherwise, reset it.
        enemy_has_catapult = False  # Not used in our current logic.

        # Run spawn logic.
        self.spawn_units(rc, main_castle_id, turn, enemy_has_catapult)

        # STEP 3: Classify our units (only Swordsmen are classified for defense/offense).
        defensive_ids, offensive_ids = self.classify_defense_offense(rc, main_castle)

        # If no threat for at least 20 consecutive turns, override classification:
        # print(self.noThreatTurns)
        # if self.noThreatTurns >= 20:
        #     # Convert all units into offensive units.
        #     offensive_ids = [uid for uid in rc.get_unit_ids(team)]
        #     defensive_ids = []
        #     self.noThreatTurns = 0
        
        # STEP 4: Defensive actions.
        # Only run defensive actions if we haven't been threat-free for a long time.
        if defensive_ids:
            self.defensive_actions(rc, defensive_ids, main_castle)
            # Release defensive units that might be blocking the spawn or attack path.
            self.release_defensive_units(rc, main_castle)
            # Clear the offensive corridor.
            self.release_offensive_path(rc, main_castle, enemy_castle)
            # Clear any remaining defensive blockages along the attack path.
            self.clear_path_for_offense(rc, defensive_ids, offensive_ids)
            # Additional step: if no enemy threat is detected, clear defensive units from the corridor.
            if not enemy_units:
                self.clear_defensive_corridor_blockers(rc, main_castle, enemy_castle)

        # BONUS: Let healers follow offensive swordsmen.
        self.support_offensive_healers(rc, offensive_ids)

        # STEP 5: Offensive actions.
        self.offensive_actions(rc, offensive_ids, enemy_castle)

        # STEP 6: Final spawn clearance: clear units from the castle tile.
        self.final_spawn_clearance(rc, main_castle)

    # ---------------------------------------------------------------------
    # HELPER FUNCTIONS
    # ---------------------------------------------------------------------
    def clear_spawn_tile(self, rc: RobotController, main_castle):
        """Move any unit (Swordsman, Catapult, or Land Healer) off the castle tile (spawn point)."""
        team = rc.get_ally_team()
        for uid in rc.get_unit_ids(team):
            unit = rc.get_unit_from_id(uid)
            if not unit:
                continue
            if unit.type in (UnitType.SWORDSMAN, UnitType.CATAPULT, UnitType.LAND_HEALER_1) and unit.x == main_castle.x and unit.y == main_castle.y:
                dirs = rc.unit_possible_move_directions(uid)
                if dirs:
                    dirs.sort(key=lambda d: -rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d),
                                                                           main_castle.x, main_castle.y))
                    best = dirs[0]
                    if rc.can_move_unit_in_direction(uid, best):
                        rc.move_unit_in_direction(uid, best)

    def spawn_units(self, rc: RobotController, main_castle_id: int, turn: int, enemy_has_catapult: bool):
        team = rc.get_ally_team()
        balance = rc.get_balance(team)
        swordsman_ids = [uid for uid in rc.get_unit_ids(team)
                      if rc.get_unit_from_id(uid) and rc.get_unit_from_id(uid).type == UnitType.SWORDSMAN]
        healer_ids = [uid for uid in rc.get_unit_ids(team)
                      if rc.get_unit_from_id(uid) and rc.get_unit_from_id(uid).type == UnitType.LAND_HEALER_1]
        num_swordsmen = len(swordsman_ids)
        num_healers = len(healer_ids)

        # Spawn swordsmen until we reach our defensive target.
        defense_sword_target = 10
        if num_swordsmen < defense_sword_target:
            if rc.can_spawn_unit(UnitType.SWORDSMAN, main_castle_id):
                rc.spawn_unit(UnitType.SWORDSMAN, main_castle_id)
                return

        # Mid/late game: spawn healers if needed.
        if turn > 50 and num_healers < 3 and balance >= 15:
            if rc.can_spawn_unit(UnitType.LAND_HEALER_1, main_castle_id):
                rc.spawn_unit(UnitType.LAND_HEALER_1, main_castle_id)
                return

        # Fallback: spawn additional swordsmen.
        if rc.can_spawn_unit(UnitType.SWORDSMAN, main_castle_id):
            rc.spawn_unit(UnitType.SWORDSMAN, main_castle_id)

    def classify_defense_offense(self, rc: RobotController, main_castle):
        team = rc.get_ally_team()
        defensive_ids = []
        offensive_ids = []
        for uid in rc.get_unit_ids(team):
            unit = rc.get_unit_from_id(uid)
            if not unit:
                continue
            if unit.type != UnitType.SWORDSMAN:
                continue
            dist = rc.get_chebyshev_distance(unit.x, unit.y, main_castle.x, main_castle.y)
            if dist <= 5:
                defensive_ids.append(uid)
            else:
                offensive_ids.append(uid)
        return defensive_ids, offensive_ids

    def defensive_actions(self, rc: RobotController, defensive_ids, main_castle):
        team = rc.get_ally_team()
        enemy = rc.get_enemy_team()
        threat_radius = 6
        enemy_units = [rc.get_unit_from_id(eid) for eid in rc.get_unit_ids(enemy) if rc.get_unit_from_id(eid)]
        threat_detected = any(rc.get_chebyshev_distance(e.x, e.y, main_castle.x, main_castle.y) <= threat_radius 
                              for e in enemy_units)
        for uid in defensive_ids:
            unit = rc.get_unit_from_id(uid)
            if not unit:
                continue
            # If enemy units are in range, attack.
            attacked = False
            for e in enemy_units:
                if not e:
                    continue
                if rc.can_unit_attack_unit(uid, e.id):
                    rc.unit_attack_unit(uid, e.id)
                    attacked = True
                    break
            if attacked:
                continue
            # If there is a threat, move toward enemy units.
            if threat_detected:
                closest = None
                closest_d = float('inf')
                for e in enemy_units:
                    d = rc.get_chebyshev_distance(unit.x, unit.y, e.x, e.y)
                    if d < closest_d:
                        closest_d = d
                        closest = e
                if closest:
                    dirs = rc.unit_possible_move_directions(uid)
                    dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d),
                                                                        closest.x, closest.y))
                    if dirs:
                        best_dir = dirs[0]
                        if rc.can_move_unit_in_direction(uid, best_dir):
                            rc.move_unit_in_direction(uid, best_dir)
            else:
                # If no threat is detected, normally defensive units hold a ring.
                desired_ring = self.get_ring_distance_for_unit(uid)
                dist = rc.get_chebyshev_distance(unit.x, unit.y, main_castle.x, main_castle.y)
                if dist < desired_ring:
                    self.move_unit_away_from(rc, uid, main_castle.x, main_castle.y)
                elif dist > desired_ring:
                    self.move_unit_toward(rc, uid, main_castle.x, main_castle.y)

    def get_ring_distance_for_unit(self, uid: int) -> int:
        """Return a desired ring distance (3, 4, or 5) based on uid."""
        return 3 + (uid % 3)

    def release_defensive_units(self, rc: RobotController, main_castle):
        team = rc.get_ally_team()
        enemy = rc.get_enemy_team()
        threat_radius = 6
        enemy_units = [rc.get_unit_from_id(eid) for eid in rc.get_unit_ids(enemy) if rc.get_unit_from_id(eid)]
        threat_detected = any(rc.get_chebyshev_distance(e.x, e.y, main_castle.x, main_castle.y) <= threat_radius 
                              for e in enemy_units)
        if not threat_detected:
            for uid in rc.get_unit_ids(team):
                unit = rc.get_unit_from_id(uid)
                if not unit:
                    continue
                if unit.type in (UnitType.SWORDSMAN, UnitType.CATAPULT) and rc.get_chebyshev_distance(unit.x, unit.y, main_castle.x, main_castle.y) < 4:
                    dirs = rc.unit_possible_move_directions(uid)
                    if dirs:
                        dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d), main_castle.x, main_castle.y), reverse=True)
                        best = dirs[0]
                        if rc.can_move_unit_in_direction(uid, best):
                            rc.move_unit_in_direction(uid, best)

    def clear_path_for_offense(self, rc: RobotController, defensive_ids, offensive_ids):
        for did in defensive_ids:
            def_unit = rc.get_unit_from_id(did)
            if not def_unit:
                continue
            for oid in offensive_ids:
                off_unit = rc.get_unit_from_id(oid)
                if not off_unit:
                    continue
                if rc.get_chebyshev_distance(def_unit.x, def_unit.y, off_unit.x, off_unit.y) < 2:
                    self.move_unit_away_from(rc, did, off_unit.x, off_unit.y)

    def release_offensive_path(self, rc: RobotController, main_castle, enemy_castle):
        dx = enemy_castle.x - main_castle.x
        dy = enemy_castle.y - main_castle.y
        norm_dx = 0 if dx == 0 else (1 if dx > 0 else -1)
        norm_dy = 0 if dy == 0 else (1 if dy > 0 else -1)
        corridor = {(main_castle.x + i * norm_dx, main_castle.y + i * norm_dy) for i in range(1, 4)}
        team = rc.get_ally_team()
        for uid in rc.get_unit_ids(team):
            unit = rc.get_unit_from_id(uid)
            if not unit:
                continue
            if unit.type in (UnitType.SWORDSMAN, UnitType.CATAPULT) and (unit.x, unit.y) in corridor:
                perp_dirs = [Direction((norm_dy, -norm_dx)), Direction((-norm_dy, norm_dx))]
                for d in perp_dirs:
                    new_x, new_y = rc.new_location(unit.x, unit.y, d)
                    if (new_x, new_y) not in corridor:
                        if rc.can_move_unit_in_direction(uid, d):
                            rc.move_unit_in_direction(uid, d)
                            break

    def clear_defensive_corridor_blockers(self, rc: RobotController, main_castle, enemy_castle):
        """
        Specifically check defensive units that remain in the corridor and move them aside so they don't block attacking units.
        """
        dx = enemy_castle.x - main_castle.x
        dy = enemy_castle.y - main_castle.y
        norm_dx = 0 if dx == 0 else (1 if dx > 0 else -1)
        norm_dy = 0 if dy == 0 else (1 if dy > 0 else -1)
        corridor = {(main_castle.x + i * norm_dx, main_castle.y + i * norm_dy) for i in range(1, 4)}
        team = rc.get_ally_team()
        for uid in rc.get_unit_ids(team):
            unit = rc.get_unit_from_id(uid)
            if not unit:
                continue
            if unit.type == UnitType.SWORDSMAN and (unit.x, unit.y) in corridor:
                possible_dirs = rc.unit_possible_move_directions(uid)
                for d in possible_dirs:
                    new_x, new_y = rc.new_location(unit.x, unit.y, d)
                    if (new_x, new_y) not in corridor and rc.can_move_unit_in_direction(uid, d):
                        rc.move_unit_in_direction(uid, d)
                        break

    def support_offensive_healers(self, rc: RobotController, offensive_ids):
        team = rc.get_ally_team()
        healer_ids = [uid for uid in rc.get_unit_ids(team)
                      if rc.get_unit_from_id(uid) and rc.get_unit_from_id(uid).type == UnitType.LAND_HEALER_1]
        if not offensive_ids or not healer_ids:
            return
        for hid in healer_ids:
            healer = rc.get_unit_from_id(hid)
            if not healer:
                continue
            closest_off = None
            closest_d = float('inf')
            for oid in offensive_ids:
                off = rc.get_unit_from_id(oid)
                if not off:
                    continue
                d = rc.get_chebyshev_distance(healer.x, healer.y, off.x, off.y)
                if d < closest_d:
                    closest_d = d
                    closest_off = off
            if closest_off and closest_d > 1:
                dirs = rc.unit_possible_move_directions(hid)
                dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(healer.x, healer.y, d),
                                                                    closest_off.x, closest_off.y))
                if dirs:
                    best = dirs[0]
                    if rc.can_move_unit_in_direction(hid, best):
                        rc.move_unit_in_direction(hid, best)

    def offensive_actions(self, rc: RobotController, offensive_ids, enemy_castle):
        if not enemy_castle:
            return
        # Get the enemy castle's ID.
        _, enemy_castle_id = rc.get_id_from_building(enemy_castle)
        # Build a sorted list of offensive unit IDs:
        sorted_offensive_ids = sorted(
            offensive_ids,
            key=lambda uid: rc.get_chebyshev_distance(
                rc.get_unit_from_id(uid).x,
                rc.get_unit_from_id(uid).y,
                enemy_castle.x,
                enemy_castle.y
            )
        )
        # Process units from closest (outermost) to farthest.
        for uid in sorted_offensive_ids:
            unit = rc.get_unit_from_id(uid)
            if not unit:
                continue
            # If the unit can attack the enemy castle directly, do so.
            if rc.can_unit_attack_building(uid, enemy_castle_id):
                rc.unit_attack_building(uid, enemy_castle_id)
            else:
                # Otherwise, look for an enemy unit to attack.
                target = None
                for eid in rc.get_unit_ids(rc.get_enemy_team()):
                    enemy_unit = rc.get_unit_from_id(eid)
                    if enemy_unit and rc.can_unit_attack_unit(uid, enemy_unit.id):
                        target = enemy_unit
                        break
                if target:
                    rc.unit_attack_unit(uid, target.id)
                else:
                    # If no attack is available, move the unit toward the enemy castle.
                    possible_dirs = rc.unit_possible_move_directions(uid)
                    if possible_dirs:
                        # Pick the direction that minimizes the distance to the enemy castle.
                        best_dir = min(
                            possible_dirs,
                            key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d),
                                                                    enemy_castle.x, enemy_castle.y)
                        )
                        if rc.can_move_unit_in_direction(uid, best_dir):
                            rc.move_unit_in_direction(uid, best_dir)

    def final_spawn_clearance(self, rc: RobotController, main_castle):
        """Ensure the castle tile is free for new spawns by moving any unit on it."""
        team = rc.get_ally_team()
        for uid in rc.get_unit_ids(team):
            unit = rc.get_unit_from_id(uid)
            if not unit:
                continue
            if unit.x == main_castle.x and unit.y == main_castle.y:
                dirs = rc.unit_possible_move_directions(uid)
                if dirs:
                    dirs.sort(key=lambda d: -rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d),
                                                                           main_castle.x, main_castle.y))
                    best = dirs[0]
                    if rc.can_move_unit_in_direction(uid, best):
                        rc.move_unit_in_direction(uid, best)

    def move_unit_away_from(self, rc: RobotController, uid: int, x: int, y: int):
        unit = rc.get_unit_from_id(uid)
        if not unit:
            return
        dirs = rc.unit_possible_move_directions(uid)
        dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d), x, y), reverse=True)
        if dirs:
            best = dirs[0]
            if rc.can_move_unit_in_direction(uid, best):
                rc.move_unit_in_direction(uid, best)

    def move_unit_toward(self, rc: RobotController, uid: int, x: int, y: int):
        unit = rc.get_unit_from_id(uid)
        if not unit:
            return
        dirs = rc.unit_possible_move_directions(uid)
        dirs.sort(key=lambda d: rc.get_chebyshev_distance(*rc.new_location(unit.x, unit.y, d), x, y))
        if dirs:
            best = dirs[0]
            if rc.can_move_unit_in_direction(uid, best):
                rc.move_unit_in_direction(uid, best)
