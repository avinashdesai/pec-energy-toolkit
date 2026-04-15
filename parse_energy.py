import xml.etree.ElementTree as ET

filepath = '/Users/avides01/Library/CloudStorage/OneDrive-Arm/Documents/Energy usage/green_button_data_1776194255990.xml'
tree = ET.parse(filepath)
root = tree.getroot()

total_value = 0
total_cost = 0
count = 0
mult_set = set()

for reading in root.iter('{http://naesb.org/espi}IntervalReading'):
    v = reading.find('{http://naesb.org/espi}value')
    m = reading.find('{http://naesb.org/espi}powerOfTenMultiplier')
    c = reading.find('{http://naesb.org/espi}cost')
    if v is not None:
        total_value += float(v.text)
        count += 1
    if m is not None:
        mult_set.add(int(m.text))
    if c is not None:
        total_cost += float(c.text)

print(f'Number of IntervalReadings: {count}')
print(f'powerOfTenMultiplier values: {mult_set}')
print(f'Raw sum of values: {total_value:.2f}')
print(f'Total energy (kWh): {total_value / 1000:.2f}')
print(f'Total cost: ${total_cost:.2f}')

# Summary info
for s in root.iter('{http://naesb.org/espi}ElectricPowerUsageSummary'):
    o = s.find('{http://naesb.org/espi}overallConsumptionLastPeriod')
    if o is not None:
        ov = o.find('{http://naesb.org/espi}value').text
        om = o.find('{http://naesb.org/espi}powerOfTenMultiplier').text
        print(f'Summary - last period consumption: {ov} (multiplier: 10^{om})')
    cur = s.find('{http://naesb.org/espi}currentBillingPeriodOverAllConsumption')
    if cur is not None:
        cv = cur.find('{http://naesb.org/espi}value').text
        cm = cur.find('{http://naesb.org/espi}powerOfTenMultiplier').text
        print(f'Summary - current period consumption: {cv} (multiplier: 10^{cm})')
    b = s.find('{http://naesb.org/espi}billLastPeriod')
    if b is not None:
        print(f'Bill last period: ${b.text}')

# Check interval duration
for reading in root.iter('{http://naesb.org/espi}IntervalReading'):
    tp = reading.find('{http://naesb.org/espi}timePeriod')
    if tp is not None:
        dur = tp.find('{http://naesb.org/espi}duration')
        if dur is not None:
            print(f'Reading interval: {dur.text} seconds ({int(dur.text)//60} min)')
            break
