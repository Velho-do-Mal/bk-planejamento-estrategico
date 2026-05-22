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
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get('next', 'planejamento:dashboard')
            return redirect(next_url)
        else:
            error = 'Usuário ou senha inválidos.'
    return render(request, 'accounts/login.html', {'error': error})


@require_http_methods(["POST"])
def logout_view(request):
    """Logout apenas via POST — previne CSRF logout attack."""
    logout(request)
    return redirect('accounts:login')


def _superuser_required(view_func):
    """Decorator: exige que o usuário seja superusuário."""
    @login_required
    def wrapper(request, *args, **kwargs):
        if not request.user.is_superuser:
            messages.error(request, 'Acesso restrito a administradores.')
            return redirect('planejamento:dashboard')
        return view_func(request, *args, **kwargs)
    return wrapper


@_superuser_required
def usuarios_view(request):
    """
    Gerenciamento de usuários — apenas superusuários.
    Permite: listar, criar, ativar/desativar, alterar senha e excluir.
    """
    error = None

    if request.method == 'POST':
        action = request.POST.get('action', '')

        # ── Criar novo usuário ──────────────────────────────────────
        if action == 'create':
            username   = request.POST.get('username', '').strip()
            first_name = request.POST.get('first_name', '').strip()
            last_name  = request.POST.get('last_name', '').strip()
            email      = request.POST.get('email', '').strip()
            password   = request.POST.get('password', '')
            password2  = request.POST.get('password2', '')
            is_staff   = request.POST.get('is_staff', '') == 'on'
            is_superuser = request.POST.get('is_superuser', '') == 'on'

            if not username:
                messages.error(request, 'Informe o nome de usuário.')
            elif Usuario.objects.filter(username=username).exists():
                messages.error(request, f'Usuário "{username}" já existe.')
            elif password != password2:
                messages.error(request, 'As senhas não conferem.')
            else:
                try:
                    validate_password(password)
                    user = Usuario.objects.create_user(
                        username=username,
                        first_name=first_name,
                        last_name=last_name,
                        email=email,
                        password=password,
                        is_staff=is_staff,
                        is_superuser=is_superuser,
                        is_active=True,
                    )
                    messages.success(
                        request,
                        f'Usuário "{username}" criado com sucesso!'
                        + (' (Administrador)' if is_superuser else '')
                    )
                except ValidationError as e:
                    messages.error(request, 'Senha fraca: ' + ' '.join(e.messages))
                except Exception as e:
                    messages.error(request, f'Erro ao criar usuário: {e}')

        # ── Ativar / desativar ──────────────────────────────────────
        elif action == 'toggle_active':
            uid = request.POST.get('user_id')
            try:
                u = Usuario.objects.get(pk=uid)
                if u == request.user:
                    messages.warning(request, 'Você não pode desativar sua própria conta.')
                else:
                    u.is_active = not u.is_active
                    u.save(update_fields=['is_active'])
                    estado = 'ativado' if u.is_active else 'desativado'
                    messages.success(request, f'Usuário "{u.username}" {estado}.')
            except Usuario.DoesNotExist:
                messages.error(request, 'Usuário não encontrado.')

        # ── Alterar senha ───────────────────────────────────────────
        elif action == 'change_password':
            uid       = request.POST.get('user_id')
            new_pass  = request.POST.get('new_password', '')
            new_pass2 = request.POST.get('new_password2', '')
            try:
                u = Usuario.objects.get(pk=uid)
                if new_pass != new_pass2:
                    messages.error(request, 'As senhas não conferem.')
                else:
                    validate_password(new_pass, user=u)
                    u.set_password(new_pass)
                    u.save()
                    messages.success(request, f'Senha de "{u.username}" alterada com sucesso.')
            except Usuario.DoesNotExist:
                messages.error(request, 'Usuário não encontrado.')
            except ValidationError as e:
                messages.error(request, 'Senha fraca: ' + ' '.join(e.messages))

        # ── Excluir usuário ─────────────────────────────────────────
        elif action == 'delete':
            uid = request.POST.get('user_id')
            try:
                u = get_object_or_404(Usuario, pk=uid)
                if u == request.user:
                    messages.warning(request, 'Você não pode excluir sua própria conta.')
                else:
                    nome = u.username
                    u.delete()
                    messages.success(request, f'Usuário "{nome}" excluído.')
            except Exception as e:
                messages.error(request, f'Erro ao excluir: {e}')

        return redirect('accounts:usuarios')

    usuarios = Usuario.objects.all().order_by('username')
    return render(request, 'accounts/usuarios.html', {'usuarios': usuarios})
