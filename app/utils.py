from datetime import datetime, timedelta

# Define the shift start times
shift_start_times = {
    "11:00 AM": datetime.strptime("11:00 AM", "%I:%M %p"),
    "03:00 PM": datetime.strptime("03:00 PM", "%I:%M %p")
}

def determine_shift(punch_time):
    if punch_time.hour < 14:  # Punch time before 2 PM is considered for the 11 AM shift
        return shift_start_times["11:00 AM"]
    else:  # Punch time from 2 PM onward is considered for the 3 PM shift
        return shift_start_times["03:00 PM"]

def calculate_deduction(row, hourly_rate):
    if row['First Punch'] == '-' or pd.isna(row['First Punch']):
        return 50, "No punch-in, Rs. 50 flat deduction"  # Deduction for not punching in
    
    # Determine first punch time
    first_punch_time = datetime.strptime(row['First Punch'], '%I:%M %p')
    
    # Determine the shift start time based on the punch time
    shift_start_time = determine_shift(first_punch_time)
    
    # Calculate delay
    delay = first_punch_time - shift_start_time

    # Calculate deduction based on delay
    if delay <= timedelta(minutes=15):
        return 0, "No deduction, within grace period"
    elif delay <= timedelta(minutes=45):
        return 50, "Late by up to 45 minutes, Rs. 50 flat deduction"
    else:
        # Deduction proportional to salary double for every hour late
        hours_late = (delay.total_seconds() / 3600) - 0.75  # Subtracting the first 45 minutes
        deduction_amount = hourly_rate * 2 * hours_late
        deduction_amount = max(50, round(deduction_amount, 2))  # Ensure minimum deduction of Rs. 50
        return deduction_amount, f"Late by {delay}, deduction: Rs. {deduction_amount:.2f} (2x salary for {hours_late:.2f} hours late)"
