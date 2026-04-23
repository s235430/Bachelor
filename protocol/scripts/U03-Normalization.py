from opentrons import protocol_api
import math

metadata = {
    "protocolName": "U03-Normalization: Resuspension dilution by CSV-defined volume",
    "author": "Rasmus Tøffner-Clausen",
    "description": (
        "Unit operation for automated media exchange in microtiter plates. "
        "For each well listed in a user-provided CSV (well, volume_ul), the protocol "
        "removes the specified volume to waste using a fresh tip, then adds the same "
        "volume of fresh resuspension medium from a reservoir back to the same well using a fresh tip. "
        "Designed for OD-based normalization and contamination-safe handling."
    ),
    "apiLevel": "2.20",
}


def add_parameters(parameters):
    parameters.add_csv_file(
        variable_name="plan_csv",
        display_name="Media dilution csv",
        description=(
            "CSV: well, volume_ul. Remove to trash then add same LB from A1; new tip per well each step."
        ),
    )


def run(protocol: protocol_api.ProtocolContext):
    
    # ----- Labware -----
    max_vol = 300
    
    plate = protocol.load_labware("nest_96_wellplate_2ml_deep", 1)

    tiprack1 = protocol.load_labware("opentrons_96_tiprack_300ul", 4)
    tiprack2 = protocol.load_labware("opentrons_96_tiprack_300ul", 5)

    reservoir = protocol.load_labware("axygen_1_reservoir_90ml", 3)
    source = reservoir.wells_by_name()["A1"]
    trash = protocol.fixed_trash

    # ----- Instruments -----
    pip = protocol.load_instrument(
        "p300_single_gen2", "right", tip_racks=[tiprack1, tiprack2]
    )

    # --- Transfer function ---
    def transfer_large_volume(pip, source, dest, volume):
        """
        Transfers uL from source to dest using equal steps.
        Splits large volumes into equal portions.
        Example: 550µL → 275 + 275
        """
        if volume <= max_vol:
            pip.aspirate(volume, source)
            pip.dispense(volume, dest)
        else:
            num_steps = math.ceil(volume / max_vol)
            step_vol = volume / num_steps
            for _ in range(num_steps):
                pip.aspirate(round(step_vol,0), source)
                pip.dispense(round(step_vol,0), dest)
                pip.blow_out()


    # ----- Parameters -----
    rows = protocol.params.plan_csv.parse_as_csv()
    
    if not rows:
        protocol.comment("CSV plan is empty → no actions.")
        return
    
    if isinstance(rows[0], list):
        header = [h.strip() for h in rows[0]]
        rows = [dict(zip(header, r)) for r in rows[1:]]

    required_cols = {"well", "volume_ul"}
    if not required_cols.issubset(set(rows[0].keys())):
        raise ValueError("CSV must contain columns: well, volume_ul")

    # -------- Step 1: REMOVE (new tip per well) --------
    for r in rows:
        well_name = str(r["well"]).strip().upper()
        vol = float(r["volume_ul"])
        if vol <= 0:
            continue

        pip.pick_up_tip()
        pip.aspirate(min(50,vol),source)
        pip.dispense(min(50,vol),source)
        src = plate.wells_by_name()[well_name]
        
        transfer_large_volume(pip, src.bottom(z = 5), trash, vol)
        
        pip.drop_tip()

    # -------- Step 2: ADD NaCl (new tip per well) --------
    for r in rows:
        well_name = str(r["well"]).strip().upper()  
        vol = float(r["volume_ul"])
        if vol <= 0:
            continue

        pip.pick_up_tip()
        pip.aspirate(min(50,vol),source)
        pip.dispense(min(50,vol),source)
        dest = plate.wells_by_name()[well_name]
        
        transfer_large_volume(pip, source, dest.top(z = - 1), vol)
        
        pip.mix(3,100, location = dest.bottom(z = 5)) 
        pip.touch_tip(speed = 5)
        
        pip.drop_tip()
