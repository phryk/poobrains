> poobrains is a webframework based on Flask,
> peewee and visions of the apocalypse.


## Kill the boilerplate ##

```python
#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import poobrains
app = poobrains.app

if __name__ == '__main__':
  app.cli()
```

This is the minimum viable poobrains site.
It comes with a CLI and folds open to a complete CMS when deployed.

This site won't be very interesting but it comes batteries included
with some basics amongst which you will find users, groups, uploads,
tags, comments and search.


## poobrains is paranoid ##

Due to the inflationary nature of this sort of statement,
let's actually look at some central points of this.


### There is no javascript. ###

No, really. 

Javascript might make the browser much more powerful, but sadly
this comes at the price of making the browser much more powerful.

It is remote code execution on the visitors computer *by design*.

While this can be used to build complex applications in the browser,
it can also be used for in-depth tracking and even serve as an infection
vector for malware.

Tor users have repeatedly been de-anonymized by malicious javascript,
for example when the FBI jacked Silk Road. # TODO: Sauce!

So, JS might be nice for developers (to a degree), but a site that
aims to protect its users privacy should really abstain from using JS,
or at least from depending on it to work.


### There are no passwords ###

Password re-use is probably the biggest security issue on the
internet today. Most people do it, it's a sad fact of life.

poobrains instead uses TLS client certificates for more granular
control and better security, thankfully handing authentication
off to the httpd.

One downside to this is that you will need to maintain a Certificate
Authority, but unless you need to integrate it into an existing CA,
poobrains will do that for you.

>   PS: I'm actually considering writing a tool to manage CAs comfortably,
>   since everything that exists sucks. Maybe in 2018…?


### Restrictive permission system ###

Permissions are restrictive. I.e. deny by default.
If seeing additive permission systems gives you the jitters,
you'll feel right at home.

It also supports permissions assigned to users as well as groups.

To add icing on the cake, it's also extensible.


### All mails GPG-encrypted ###

The mail system has been written such that it doesn't even know how to
send unencrypted mails. Be thankful for that, wrangling GPG is a horrible
fucking experience.


## Usability is still a big priority ##

Yes, the aforementioned things impose some limits you don't usually have.
This is not without reason tho and a great deal of work went (and will
continue to go) into making poobrains usable.

The default theme makes extensive use of HTML5 semantics and is fully
responsive down to about 320x480.

But poobrains commitment to usability does not stop with the web user;
Developer eXperience is a central part of the development ethos, too.

It (hopefully) leverages inheritance-as-an-API in a way that makes
adding new content types and features less of a hassle.


## The most important base classes ##

These are the most important things you can subclass.

###Renderable###

Defined in [poobrains.rendering][documentation/poobrains.rendering]. 

Renderables are objects that can be rendered to text by a template.
This is mostly used to create HTML but there's templatable SVG, too.


### Storable ###

Defined in [poobrains.storage][documentation/poobrains.storage] .

A subclass of `Renderable` that is also an ORM Model corresponding
to a single table in the database. Instances can be saved and retrieved
as rows in that table.


### Protected ###

Defined in [poobrains.auth][documentation/poobrains.auth].

A subclass of `Renderable` that performs permission checks before
letting a user view it.


### Administerable ###

Defined in [poobrains.auth][documentation/poobrains.auth].

A subclass of `Storable` and `Protected` that also uses the integrated
form system to offer administration features to add, edit and delete
instances.


## A small sensible site ##

Now that we know a bit more, let's make a more sensible tiny site, shall we?

```python
#!/usr/bin/env python2.7
# -*- coding: utf-8 -*-

import poobrains
app = poobrains.app


@app.export('/post/')
class Post(poobrains.auth.Administerable):

    title = poobrains.storage.fields.CharField()
    text = poobrains.storage.fields.MarkdownField()


if __name__ == '__main__':
  app.cli()
```

Adding a new `Administerable` subclass is all that's needed to add a
new content type that can be administered on-site.

The `app.expose` class decorator is a neat little shortcut that puts
a paginated list of `Post` at `/post/` with single instances/rows being
available under `/post/\<postname\>` (ex: `/post/foo` for `Post` "foo")


## Actual deployment ##

So, we wrote the code for a tiny site up there, but how do we
actually get this thing running?


### Dependencies ###

While poobrains python dependencies are taken care of by pip, there are a few
external dependencies you'll need:

- python-2.7

- pip for python-2.7

- gnupg-2.0
    - The 2.0 part is important, since 2.1 has the habit of adding
      new output codes that libraries don't handle *\*shakes fist at gpg\**

- an httpd that supports TLS client certificate authentication
    - When in doubt, choose nginx
    - Apache should (untested) work too, but poobrains doesn't
      yet autogenerate apache configurations
    - If you're thinking about deploying with any other httpd,
      you already know more about it than I do. What you need
      is for it to pass TLS client certificate authentication
      status and the cert to the web application for every request.


### Directory structure ####

Create a new directory for the project and put the file
with the above code there, so you have a structure like:

- `site/` the directory we created
    - `site.py` the .py file with our code

> The rest of this quickstart will assume the shown naming,
> but you are free to choose whatever names you want.


### virtualenv ###

You can run a poobrains-based site without virtualenv, but doing so
is expected to be the default case. If you don't know what virtualenvs
are or are unsure, just roll with it for now.

Change to the created directory:
`cd site`

Create the virtualenv:
`virtualenv --system-site-packages .`

`--system-site-packages` is not needed, but will enable your virtualenv to use
python libraries installed on your system.

Activate the virtualenv:
`source bin/activate[.yourshell]`

If it worked, you'll see `(site)` at the beginning of your terminal prompt.


### Installing poobrains ###

`pip install 'git+https://github.com/phryk/poobrains'`

This will install poobrains and all needed python dependencies.


### Installing the site ###

The installation procedure is called through your sites CLI.

To access it, make your codefile executable (`chmod +x site.py`).
(I mean you could just call it with the `python` interpreter directly,
but that's way less l33t.)

Now, kick off the installation procedure of your site by executing:
`./site.py install`

The installation procedure will ask your for a few pieces of info and then
build the database, add default users and groups, create a `config.py` along
with other config files dependant on your chosen deployment and OS combination
and create a GPG homedir.

Make sure that your machine is reachable under whatever you input as `domain`.
If you use the default `localhost`, this will work without further intervention.

If you don't have a mail account at hand for the site to use, just put in
rubbish values for those inputs.

For the `deployment` input, this quickstart assumes the default `uwsgi+nginx`
value. You can use `custom` if you want to create the httpd config yourself,
but obviously that's more work.

In this case, you'll see files called `site.nginx.conf` as well as `site.ini`
have appeared next to your site.py after the installation procedure went through.

You can use `site.nginx.conf` verbatim as your nginx.conf if you don't
want to run anything besides this site, otherwise, you'll just want to
add the `server` directive in there and ignore the caching stuff in
the `http` block for now. 

*Please note that unless you went through "Creating a CA", nginx will not accept this config.*

The `site.ini` can be placed in a directory uwsgi watches for ini files
(`[usr/local]/etc/uwsgi.d`, probably) or just be used directly by running
`uwsgi --strict site.ini`

Please also note that the installation procedure gives you a text token
needed for the creation of your first client certificate needed to log
in as administrator - it's the thing that's bold and cybre-colored.
It's a random string, but let's just say it was `MEANSOFPRODUCTION`.
We'll need it later.


### Creating a CA ###

poobrains' CLI offers the `minica` command to create a minimum viable
CA with a single certificate that acts as both CA and server certificate.
Don't worry if you didn't understand that, just know that without a CA
you won't ever be able to log into your site.

So, execute
`./site.py minica`

Now, you'll have the CA in `site/tls/` and that's exactly where
`site.nginx.conf` expects it to be.


### Permissions ###

We will need to make sure that some things have the right permissions.
Assuming the httpd will run as group `www`, do:

`chgrp -R www .`  
`chmod g+rwx .`  
`chmod g+rw site.db`  
`chmod -R g+rw upload`  


### Starting up ###

Everything is in place. Start up nginx and uwsgi, using `service`, `systemctl`
or whatever contraption your OS uses.


## First visit and client certificate ##

Your site is now reachable! Browse to `https://localhost/cert/`
and let the browser guide you through adding an exception for the
certificate we created with the `minica` command.

And now we got… a pretty 404 page!

This is normal since a good deal of the "booting" process of poobrains
is done on the first request.

Reload the page and you'll get a small form with 3 buttons.

Remember the text token we talked about earlier? `MEANSOFPRODUCTION`?
Put that into the text field of the form and…


### If you're on Firefox ###

Click the "Client-side: Keygen" Button. You should now see a notification
dialogue telling you that your client certificate has been added to the browser.

Clear the history with 'Active Logins' checked and reload the page.
You are now greeted by a dialogue window to choose the client certificate
to use for the login. Choose your certificate and click OK.


### If you're using any other browser ###

Click the "Server-Side: HTTPS" button. You will get a download,
save it as a .p12 file and then reload the page to get the
passphrase needed to use this file.

Now, you'll need to import the .p12 file as certificate into your browser.
This is usually somewhere in an 'advanced' or 'security' section of the
browser settings.

On import, the browser will ask you for the passphrase of the .p12 file,
copy it into the dialogue, click okay and you should be done.

> You might have to clear the browser history, or even restart the browser,
> but maybe it's enough to just…

Reload the page. You should be seeing a dialogue asking you to choose a
certificate for authentication. Choose your imported certificate and click OK.


### Got a "No such token" error? ###

So you either forgot the right token or the token expired (it does that).
No problem, just add another one through the CLI:

`./site.py add clientcerttoken`

The user you want to choose is `root`, for everything else, just use the
suggested defaults.

After the command is finished, repeat the procedure with the new token.


### Congratulations ###

If you are seeing a dashbar at the top of the page, you are now logged
in as the main administrator of the site. If you wish, you can go and
explore a bit now - I'll be here when you come back.


### BONUS ROUND ###

Bug the developers of your browser to make TLS client certificate
authentication more comfortable to use. Demand usable security!


## Babbys first template ##

You might've already noticed that when adding a new `Post` and trying
to view it, instead of the `text` field, we get some generic message
about templates.

To rectify this situation, we have to add a template for `Post`
to the project.

Just getting the markdown of the `text` field rendered can be done
by creating this template file under `site/themes/default/post.jinja`:

```
{% extends "administerable.jinja" %}

{% block content %}
    {{ content.text.render() }}
{% endblock %}
```

The language you're seeing is jinja2 and if you're confused about this,
check out jinja2s nice [template designer documentation][jinja-templates]


[jinja-templates]: https://jinja.pocoo.org/docs/templates/


## Markdown ##

So, I'm guessing you might've figured out that poobrains has markdown
support. It does however extend markdown in two neat ways.

Any markdown can refererence any specific `Renderable`.
Let's look at what that means:

If you put `[video/to-change-everything]` into the `text` field
of a `Post`, it will be substituted by a link to the video with
the name `to-change-everything`, but only if:

- a video by that name exists
*AND*
- the visitor viewing the post is allowed to view that video

Even better, `![video/to-change-everything]` will be substituted
by a rendered version of the `video` instance, i.e. a `<video>` tag.

For example: ![video/to-change-everything]


## poobrains permissions ##

We have a site, we can view, add, edit and delete content.
But remember the part about paranoia and a "restrictive"
permission system?

When a poobrains site is visited without without a TLS client
certificate, it loads the user `anonymous` and uses that
for permission checks done in the context of these requests.

In order to allow the `anonymous` user to access `Post`s,
enter the Admin Area, select "UserPermission" and then
"add new UserPermission".

Enter "anonymous" as user (the text field does auto-completion).

Open the `<select>` (the dropdown thingamabob in the form),
scroll down to `Post_create` and select `Grant`.

Finally, click the "Save" button.


## SO MUCH MOAR ##

We covered a good bit of ground in here. Pat yourself on the back.
Relax a bit. BREATHE, GODDAMMIT!

There's a lot more to poobrains and I'll get into these things
at a later point, but currently most effort will be focused on
working toward the first alpha version.

Amongst the features we didn't even talk about here:

- instance-specific permissions
- hierarchic tags
- threadable comments
- SCSS integration
- templatable SVG
    - this includes dataset plots and simple maps
    - honors themes by means of the SCSS integration
