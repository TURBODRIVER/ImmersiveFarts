import inspect
import math
import random
from functools import wraps

import alarms
import objects.components.types
import services
from audio.primitive import PlaySound
from broadcasters.broadcaster_request import BroadcasterRequest
from clock import ClockSpeedMode
from date_and_time import TimeSpan
from interactions import ParticipantType
from sims.sim_info_types import Species, Age
from sims4.resources import Types
from vfx import PlayEffect
from zone import Zone

FART_ALARM = None


# Changelog
# 1.1
# - Excluded Servo Sims, Neat Sims, and Good Manners Sims from farting
# 1.0
# - Initial Release

class FartAlarm():
    INTERVAL_RATE = 2  # Run every INTERVAL_RATE attempts to decrease number of runs for performance gain
    FART_INTERVAL_PER_SIM = 7500 * INTERVAL_RATE
    FART_CHANCE_BASE = 20

    ALLOWED_CLOCK_SPEEDS = {
        ClockSpeedMode.NORMAL,
        ClockSpeedMode.SPEED2,
        ClockSpeedMode.SPEED3,
    }

    DISALLOWED_TRAITS = {
        251970,  # trait_Proper
        218444,  # trait_Humanoid_Robots_MainTrait
        16858,  # trait_Neat
        160841,  # trait_LifeSkills_GoodManners
    }

    BLADDER_MOTIVE_STATISTIC = 16652  # motive_Bladder

    def __init__(self):
        self.alarm = alarms.add_alarm(self, TimeSpan(self.FART_INTERVAL_PER_SIM), self.alarm_callback, repeating=True, cross_zone=True)
        self.interval_count = 0

    def alarm_callback(self, _):
        if services.game_clock_service().clock_speed not in self.ALLOWED_CLOCK_SPEEDS:
            return

        self.interval_count += self.INTERVAL_RATE

        instanced_sims = self._get_instanced_sims()

        if self.interval_count > len(instanced_sims):
            self.interval_count = 0

            if random.random() <= len(instanced_sims) / self.FART_CHANCE_BASE:
                (sim_instance, _) = self.get_fart_participant(instanced_sims)

                if sim_instance is not None:
                    self.invoke_fart(sim_instance)

    def get_fart_participant(self, instanced_sims):
        bladder_motive_type = services.get_instance_manager(Types.STATISTIC).get(self.BLADDER_MOTIVE_STATISTIC)

        available_participants = []

        for sim_instance in instanced_sims:
            # Disallow Sims with specific traits
            if any(getattr(trait, 'guid64', 0) in self.DISALLOWED_TRAITS for trait in sim_instance.sim_info.get_traits()):
                continue

            # Bladder Motive
            bladder_motive = None

            statistics_component = sim_instance.sim_info.get_component(objects.components.types.STATISTIC_COMPONENT)

            if statistics_component is not None:
                statistics_tracker = statistics_component.get_tracker(bladder_motive_type)

                if statistics_tracker is not None:
                    statistic = statistics_tracker.get_statistic(bladder_motive_type)

                    if statistic is not None:
                        bladder_motive = statistic.get_value()

            if bladder_motive is not None:
                available_participants.append((sim_instance, bladder_motive))

        if available_participants:
            # Sort based on bladder motive and choose from first half of sorted result
            available_participants.sort(key=lambda x: x[1])
            available_participants = available_participants[:max(1, math.ceil(len(available_participants) / 2))]

            return random.choice(available_participants)

        return (None, None)

    def invoke_fart(self, sim_instance):
        PlayEffect(sim_instance, effect_name='ep1_gas_fart', joint_name=0x556B181A).start()
        PlaySound(sim_instance, 0x813614B62E50B00B).start()  # mischief_youfarted

        # Only broadcast smell inside buildings
        if sim_instance.is_inside_building:
            broadcaster_request = FartBroadcasterRequest(sim_instance)

            if broadcaster_request.has_broadcaster_resource():
                broadcaster_request.start_one_shot()

    def _get_instanced_sims(self):
        instanced_sims = []

        for sim_info in services.sim_info_manager().get_all():
            if sim_info is not None:
                if sim_info.species != Species.HUMAN:
                    continue

                if sim_info.age < Age.CHILD:
                    continue

                sim_instance = sim_info.get_sim_instance()

                if sim_instance is not None:
                    instanced_sims.append(sim_instance)

        return instanced_sims


class FartBroadcasterRequest(BroadcasterRequest):
    REACTION_BROADCASTER = 13350548967386559723  # ImmersiveFarting_Broadcaster_Reaction_SmellFart

    def __init__(self, *args, **kwargs):
        self.fart_broadcaster_type = services.get_instance_manager(Types.BROADCASTER).get(self.REACTION_BROADCASTER)

        self.broadcaster_types = lambda *_, **__: (self.fart_broadcaster_type,)
        self.participant = ParticipantType.Actor
        self.offset_time = 2.0

        super().__init__(*args, **kwargs)

    def has_broadcaster_resource(self):
        return self.fart_broadcaster_type is not None


def initiate_fart_alarm():
    global FART_ALARM

    if FART_ALARM is None:
        FART_ALARM = FartAlarm()


def inject(target_object, target_function_name, safe=False):
    if safe and not hasattr(target_object, target_function_name):
        def _self_wrap(wrap_function):
            return wrap_function

        return _self_wrap

    def _wrap_original_function(original_function, new_function):
        @wraps(original_function)
        def _wrapped_function(*args, **kwargs):
            if type(original_function) is property:
                return new_function(original_function.fget, *args, **kwargs)
            else:
                return new_function(original_function, *args, **kwargs)

        if inspect.ismethod(original_function):
            return classmethod(_wrapped_function)
        elif type(original_function) is property:
            return property(_wrapped_function)
        else:
            return _wrapped_function

    def _injected(wrap_function):
        original_function = getattr(target_object, target_function_name)
        setattr(target_object, target_function_name, _wrap_original_function(original_function, wrap_function))

        return wrap_function

    return _injected


@inject(Zone, 'do_zone_spin_up')
def _immersive_farting_on_late_zone_load(original, self, *args, **kwargs):
    try:
        result = original(self, *args, **kwargs)
    except:
        result = None

    try:
        initiate_fart_alarm()
    except:
        pass

    return result
