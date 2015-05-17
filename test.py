from projectname import ProjectName, BaseModel

app = ProjectName('ProjectName')

class TestA(BaseModel):
    pass

class TestB(BaseModel):
    pass

class TestB1(TestB):
    pass

if __name__ == '__main__':
    print "children: ", BaseModel.children()
    app.run()
