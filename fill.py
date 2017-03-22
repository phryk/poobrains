import example

u = example.poobrains.auth.User.load('administrator')
g = example.poobrains.auth.Group.load('administrators')

for i in range(0, 100):

    n = example.News()
    n.name = "test-%d" % i
    n.title = "Test #%d" % i
    n.text = "Blargh."
    n.owner = u
    n.group = g
    n.save()
    print "Saved News test-%d" % i
