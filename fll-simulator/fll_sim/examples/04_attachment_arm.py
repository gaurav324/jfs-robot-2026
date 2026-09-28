# Drive to a mission model, then run an attachment motor to lift an arm.
# The drive base is A + B; the attachment motor is on port 'F'.
from spike import PrimeHub, MotorPair, Motor
from spike.control import wait_for_seconds

hub = PrimeHub()
drive = MotorPair('A', 'B')
arm = Motor('F')

drive.set_default_speed(40)
drive.move(60, 'cm')            # drive up to the model

print("Raising the arm...")
arm.run_for_degrees(180, speed=50)   # lift
wait_for_seconds(0.3)
arm.run_for_degrees(-180, speed=50)  # lower again

drive.move(20, 'cm', steering=-30)   # curve away
print("Attachment position:", arm.get_degrees_counted(), "degrees")
