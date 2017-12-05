import math
import example


u = example.poobrains.auth.User.load('root')
g = example.poobrains.auth.Group.load('administrators')


def fill_news():
    for i in range(0, 100):

        n = example.News()
        n.name = "test-%d" % i
        n.title = "Test #%d" % i
        n.text = "Blargh."
        n.owner = u
        n.group = g
        n.save()
        print "Saved News test-%d" % i


def fill_datasets():

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
        fuck.y = 0

        fuck.save(force_insert=True)


def fill_map():

    m = example.poobrains.svg.MapDataset()
    m.owner = u
    m.group = g
    m.name = 'test'
    m.title = 'Test'
    m.description = 'Test MapDataset automatically created from fill.py'
    m.save()

    for lat in range(-90, 91, 10):
        for lon in range(-180, 181, 10):
            dp = example.poobrains.svg.MapDatapoint()
            dp.owner = u
            dp.group = g
            dp.dataset = m
            dp.name = 'test-%d-%d' % (lat, lon)
            dp.title = 'Zee test at %d / %d' % (lat, lon)
            dp.description = 'Test marker on map at %d %d' % (lat, lon)
            dp.latitude = lat
            dp.longitude = lon

            dp.save(force_insert=True)
