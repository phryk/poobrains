import math
import random
import example


u = example.poobrains.auth.User.load('root')
g = example.poobrains.auth.Group.load('administrators')


def news():
    for i in range(0, 100):

        n = example.News()
        n.name = "test-%d" % i
        n.title = "Test #%d" % i
        n.text = "Blargh."
        n.owner = u
        n.group = g
        n.save()
        print "Saved News test-%d" % i


def datasets():

    sine = example.poobrains.svg.Dataset()
    sine.owner = u
    sine.group = g
    sine.name = 'sine'
    sine.title = 'Give me a sine'
    sine.description = 'And Eris spoke "Okay, I guess."'
    sine.label_x = 'Sine X'
    sine.label_y = 'Sine Y'
    sine.save()

    fucksgiven = example.poobrains.svg.Dataset()
    fucksgiven.owner = u
    fucksgiven.group = g
    fucksgiven.name = 'fucksgiven'
    fucksgiven.title = 'Fucks given'
    fucksgiven.description = "Fucks given over time"
    fucksgiven.label_x = "Time"
    fucksgiven.label_y = "Fucks given"
    fucksgiven.save()

    sine_steps = 33
    for i in range(0,sine_steps):

        dp = example.poobrains.svg.Datapoint()
        dp.dataset = sine
        dp.owner = u
        dp.group = g
        dp.x = i
        dp.y = math.sin(i/float(sine_steps-1) * 2 * math.pi)

        dp.save(force_insert=True)


        fuck = example.poobrains.svg.Datapoint()
        fuck.dataset = fucksgiven
        fuck.owner = u
        fuck.group = g
        fuck.x = i
        fuck.y = random.randint(-100,100) / 100.0
        if fuck.y < 0:
            fuck.error_upper = abs(fuck.y)
        else:
            fuck.error_lower = abs(fuck.y)

        fuck.save(force_insert=True)

    cont_a = example.poobrains.svg.Dataset()
    cont_a.owner = u
    cont_a.group = g
    cont_a.name = 'cont_a'
    cont_a.title = 'Continued thingie A'
    cont_a.description = "The first of a two part plot thingamabob"
    cont_a.label_x = "Florp"
    cont_a.label_y = "Plonk"
    cont_a.save()

    for i in range(-23, 6):

        dp = example.poobrains.svg.Datapoint()
        dp.dataset = cont_a
        dp.owner = u
        dp.group = g
        dp.x = i
        dp.y = random.random()

        dp.save(force_insert=True)

    cont_b = example.poobrains.svg.Dataset()
    cont_b.owner = u
    cont_b.group = g
    cont_b.name = 'cont_b'
    cont_b.title = 'Continued thingie B'
    cont_b.description = "The **second** part of a two part plot thingamabob"
    cont_b.label_x = "Florp"
    cont_b.label_y = "Plonk"
    cont_b.save()

    for i in range(2, 24):

        dp = example.poobrains.svg.Datapoint()
        dp.dataset = cont_b
        dp.owner = u
        dp.group = g
        dp.x = i
        dp.y = random.random()

        dp.save(force_insert=True)


def map():

    m = example.poobrains.svg.MapDataset()
    m.owner = u
    m.group = g
    m.name = 'grid'
    m.title = 'Grid'
    m.description = 'Markers every 30 degrees. Automatically created from fill.py.'
    m.save()

    for lat in range(-75, 76, 15):
        for lon in range(-180, 181, 15):
            dp = example.poobrains.svg.MapDatapoint()
            dp.owner = u
            dp.group = g
            dp.dataset = m
            dp.title = 'Zee test at %d / %d' % (lat, lon)
            dp.description = 'Test marker on map at %d %d' % (lat, lon)
            dp.latitude = lat
            dp.longitude = lon

            dp.save(force_insert=True)

    places = example.poobrains.svg.MapDataset()
    places.owner = u
    places.group = g
    places.name = 'places'
    places.title = 'Some Places'
    places.description = 'Sample MapDataset from fill.py'
    places.save()

    dp = example.poobrains.svg.MapDatapoint()
    dp.owner = u
    dp.group = g
    dp.dataset = places
    dp.latitude = 0
    dp.longitude = 0
    dp.title = 'Center'
    dp.description = 'Center of the map at 0,0. Near the african west coast.'
    dp.save(force_insert=True)

    dp = example.poobrains.svg.MapDatapoint()
    dp.owner = u
    dp.group = g
    dp.dataset = places
    dp.latitude = 51.34897
    dp.longitude = 12.37115
    dp.title = 'Leipzig'
    dp.description = 'Where 34C3 will be'
    dp.save(force_insert=True)

    dp = example.poobrains.svg.MapDatapoint()
    dp.owner = u
    dp.group = g
    dp.dataset = places
    dp.latitude = 8.0817
    dp.longitude = 77.5497
    dp.title = 'Kanyakumari'
    dp.description = 'Southernmost town of mainland India'
    dp.save(force_insert=True)
    
    dp = example.poobrains.svg.MapDatapoint()
    dp.owner = u
    dp.group = g
    dp.dataset = places
    dp.latitude = -41.86385
    dp.longitude = 146.73089
    dp.title = 'Great Lake'
    dp.description = '"Great Lake" in Tansania (or rather a tiny island on it)'
    dp.save(force_insert=True)
