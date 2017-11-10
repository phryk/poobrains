import math
import example


u = example.poobrains.auth.User.load('root')
g = example.poobrains.auth.Group.load('administrators')

#for i in range(0, 100):
#
#    n = example.News()
#    n.name = "test-%d" % i
#    n.title = "Test #%d" % i
#    n.text = "Blargh."
#    n.owner = u
#    n.group = g
#    n.save()
#    print "Saved News test-%d" % i


dataset = example.poobrains.svg.Dataset()
dataset.owner = u
dataset.group = g
dataset.name = 'sine'
dataset.title = 'Give me a sine'
dataset.description = 'And Eris spoke "Okay, I guess."'
dataset.x_label = 'EX'
dataset.y_label = 'VAI'
dataset.save()

for i in range(0,1000):

    dp = example.poobrains.svg.Datapoint()
    dp.dataset = dataset
    dp.x = i
    dp.y = math.sin(i*0.05)

    dp.save(force_insert=True)
