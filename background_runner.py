# -*- coding: utf-8 -*-
import time
import subprocess
import os

print("BehavioralShield Advanced Power-Saving & Motion-Triggered Mode imewashwa...")

def check_call_state():
    try:
        output = subprocess.check_output("termux-telephony-callstate", shell=True, text=True)
        return "OFFHOOK" in output or "RINGING" in output
    except:
        return False

def is_screen_on():
    try:
        output = subprocess.check_output("dumpsys power | grep 'mHolding'", shell=True, text=True)
        return "true" in output.lower() or "Awake" in output
    except:
        return True

def check_motion():
    try:
        # Inasoma sensorer kupitia Termux API kuangalia kama simu inatembea/inasogezwa
        output = subprocess.check_output("termux-sensor -s accelerometer -n 1", shell=True, text=True)
        # Kama thamani za mabadiliko ya mwelekeo zipo juu ya kiwango fulani, simu inatembea
        if "values" in output:
            # Unaweza kuweka mantiki ya usomaji wa mwelekeo hapa
            return True
    except:
        pass
    return False

last_screen_state = False
last_regular_check = time.time()
REGULAR_INTERVAL = 600  # Sekunde 600 = Dakika 10

while True:
    try:
        current_screen_on = is_screen_on()
        
        # SHERIA YA 2: Ukipiga au kupigiwa simu -> Jifunze kwa dakika 2 mfululizo
        if check_call_state():
            print("Tukio la Simu: Inajifunza kwa dakika 2...")
            start_learn = time.time()
            while time.time() - start_learn < 120:
                if not check_call_state():
                    break
                subprocess.run(["python3", "/data/data/com.termux/files/home/BehavioralShield/cloud_sync.py"])
                time.sleep(2)
            print("Muda wa simu umekwisha. Inapumzika.")
            time.sleep(10)

        # SHERIA YA 1: Kioo kimetoka kuzimwa kwenda kuwashwa -> Jifunze kwa sekunde 10 bila kupumzika
        elif current_screen_on and not last_screen_state:
            print("Kioo kimewashwa: Inajifunza kwa sekunde 10...")
            start_10s = time.time()
            while time.time() - start_10s < 10:
                subprocess.run(["python3", "/data/data/com.termux/files/home/BehavioralShield/cloud_sync.py"])
                time.sleep(1)
            last_regular_check = time.time()

        # SHERIA YA 3: Kioo kikiwa kimewashwa muda wote -> Sekunde 4 kila baada ya dakika 10
        elif current_screen_on:
            if time.time() - last_regular_check >= REGULAR_INTERVAL:
                print("Kioo kimewashwa muda wote: Ukaguzi wa sekunde 4...")
                start_4s = time.time()
                while time.time() - start_4s < 4:
                    subprocess.run(["python3", "/data/data/com.termux/files/home/BehavioralShield/cloud_sync.py"])
                    time.sleep(1)
                last_regular_check = time.time()

        # SHERIA YA 4: Kioo kikiwa kimesimama/kimezimwa
        else:
            # Angalia kama simu inatembea (mfukoni) au imetulia
            if check_motion():
                if time.time() - last_regular_check >= REGULAR_INTERVAL:
                    print("Simu inatembea (mfukoni) na kioo kimezimwa: Ukaguzi wa sekunde 4...")
                    start_4s = time.time()
                    while time.time() - start_4s < 4:
                        subprocess.run(["python3", "/data/data/com.termux/files/home/BehavioralShield/cloud_sync.py"])
                        time.sleep(1)
                    last_regular_check = time.time()
            else:
                # Imewekwa sehemu tulivu na kioo kimezimwa -> ISIIWASHE HATA KIDOGO (Sleep ndefu)
                pass

        last_screen_state = current_screen_on
        time.sleep(3)

    except Exception as e:
        print(f"Hitilafu: {e}")
        time.sleep(10)
