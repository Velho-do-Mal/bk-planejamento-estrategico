from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.contrib import messages

Usuario = get_user_model()


def login_view(request):
    if request.user.is_authenticated:
        return redirect('planejamento:dashboard')
    error = None
    if request.method == 'POST':
        username = request.POST.get('username','').strip()
        password = request.POST.get('password','')
        user = authenticate(request, username=username, password=password)
        if user:
            if not user.is_active:
                error = 'Sua conta está desativada. Contate o administrador.'
            elif user.empresa and not user.empresa.ativa:
                error = 'Sua empresa está inativa. Contate o suporte.'
            else:
                login(request, user)
                return redirect(request.GET.get('next','planejamento:dashboard'))
        else:
            error = 'Usuário ou senha inválidos.'
    return render(request, 'accounts/login.html', {'error': error})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect('accounts:login')


def registro_view(request):
    """Cadastro público — cria empresa + primeiro usuário (plano free)."""
    from apps.planejamento.models import Empresa, PlanningData
    if request.user.is_authenticated:
        return redirect('planejamento:dashboard')
    if request.method == 'POST':
        nome_empresa = request.POST.get('nome_empresa','').strip()
        responsavel  = request.POST.get('responsavel','').strip()
        email        = request.POST.get('email','').strip()
        username     = request.POST.get('username','').strip()
        password     = request.POST.get('password','')
        password2    = request.POST.get('password2','')
        telefone     = request.POST.get('telefone','').strip()

        if not nome_empresa: messages.error(request,'Informe o nome da empresa.'); return render(request,'accounts/registro.html',{})
        if not username:      messages.error(request,'Informe o usuário.'); return render(request,'accounts/registro.html',{})
        if password != password2: messages.error(request,'As senhas não conferem.'); return render(request,'accounts/registro.html',{})
        if Usuario.objects.filter(username=username).exists():
            messages.error(request,f'Usuário "{username}" já existe. Escolha outro.'); return render(request,'accounts/registro.html',{})

        try:
            validate_password(password)
        except ValidationError as e:
            messages.error(request,'Senha fraca: ' + ' '.join(e.messages)); return render(request,'accounts/registro.html',{})

        try:
            slug = Empresa.gerar_slug(nome_empresa)
            empresa = Empresa.objects.create(slug=slug, nome=nome_empresa, plano='free',
                                              ativa=True, email=email, telefone=telefone,
                                              responsavel=responsavel)
            PlanningData.get_or_create_for(empresa)
            user = Usuario.objects.create_user(username=username, password=password,
                                               email=email, empresa=empresa,
                                               first_name=responsavel.split()[0] if responsavel else '',
                                               last_name=' '.join(responsavel.split()[1:]) if responsavel else '',
                                               is_staff=False, is_superuser=False)
            login(request, user)
            messages.success(request,f'Bem-vindo(a) ao BK Planejamento! Empresa "{nome_empresa}" criada no Plano Free.')
            return redirect('planejamento:dashboard')
        except Exception as e:
            messages.error(request,f'Erro ao criar conta: {e}')
    return render(request,'accounts/registro.html',{})


def _superuser_required(view_func):
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request,'Acesso restrito a administradores.'); return redirect('planejamento:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@_superuser_required
def usuarios_view(request):
    """Gerenciamento de usuários — apenas superusuários."""
    from apps.planejamento.models import Empresa
    if request.method == 'POST':
        action = request.POST.get('action','')
        if action == 'create':
            username=request.POST.get('username','').strip(); email=request.POST.get('email','').strip()
            first_name=request.POST.get('first_name','').strip(); last_name=request.POST.get('last_name','').strip()
            password=request.POST.get('password',''); password2=request.POST.get('password2','')
            is_staff=request.POST.get('is_staff','')=='on'; is_superuser=request.POST.get('is_superuser','')=='on'
            empresa_id=request.POST.get('empresa_id')
            if not username: messages.error(request,'Informe o usuário.')
            elif Usuario.objects.filter(username=username).exists(): messages.error(request,f'Usuário "{username}" já existe.')
            elif password != password2: messages.error(request,'Senhas não conferem.')
            else:
                try:
                    validate_password(password)
                    empresa = Empresa.objects.get(pk=empresa_id) if empresa_id else None
                    Usuario.objects.create_user(username=username,first_name=first_name,last_name=last_name,
                        email=email,password=password,is_staff=is_staff,is_superuser=is_superuser,
                        is_active=True,empresa=empresa)
                    messages.success(request,f'Usuário "{username}" criado!')
                except ValidationError as e: messages.error(request,'Senha fraca: '+' '.join(e.messages))
                except Exception as e: messages.error(request,f'Erro: {e}')
        elif action == 'toggle_active':
            try:
                u = Usuario.objects.get(pk=request.POST.get('user_id'))
                if u == request.user: messages.warning(request,'Não é possível desativar sua própria conta.')
                else:
                    u.is_active = not u.is_active; u.save(update_fields=['is_active'])
                    messages.success(request,f'Usuário "{u.username}" {"ativado" if u.is_active else "desativado"}.')
            except Usuario.DoesNotExist: messages.error(request,'Usuário não encontrado.')
        elif action == 'change_password':
            uid=request.POST.get('user_id'); p1=request.POST.get('new_password',''); p2=request.POST.get('new_password2','')
            try:
                u = Usuario.objects.get(pk=uid)
                if p1 != p2: messages.error(request,'Senhas não conferem.')
                else:
                    validate_password(p1,user=u); u.set_password(p1); u.save()
                    messages.success(request,f'Senha de "{u.username}" alterada.')
            except Usuario.DoesNotExist: messages.error(request,'Usuário não encontrado.')
            except ValidationError as e: messages.error(request,'Senha fraca: '+' '.join(e.messages))
        elif action == 'delete':
            try:
                u = get_object_or_404(Usuario,pk=request.POST.get('user_id'))
                if u == request.user: messages.warning(request,'Não é possível excluir sua própria conta.')
                else: nome=u.username; u.delete(); messages.success(request,f'Usuário "{nome}" excluído.')
            except Exception as e: messages.error(request,f'Erro: {e}')
        return redirect('accounts:usuarios')
    from apps.planejamento.models import Empresa
    return render(request,'accounts/usuarios.html',{
        'usuarios': Usuario.objects.all().order_by('username'),
        'empresas': Empresa.objects.filter(ativa=True).order_by('nome'),
    })
