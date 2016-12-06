from contextlib import contextmanager
from functools import partial

from langkit import names
from langkit.compiled_types import (
    EnvElement, LexicalEnvType, Token, BoolType, T
)
from langkit.diagnostics import check_source_language
from langkit.expressions.base import (
    AbstractVariable, AbstractExpression, ArrayExpr, BuiltinCallExpr,
    ResolvedExpression, construct, PropertyDef, BasicExpr, auto_attr, Self,
    auto_attr_custom
)


class EnvVariable(AbstractVariable):
    """
    Singleton abstract variable for the implicit environment parameter.
    """

    def __init__(self):
        super(EnvVariable, self).__init__(
            names.Name("Current_Env"),
            type=LexicalEnvType
        )
        self._is_bound = False

    @property
    def has_ambient_env(self):
        """
        Return whether ambient environment value is available.

        If there is one, this is either the implicit environment argument for
        the current property, or the currently bound environment (using
        eval_in_env).

        :rtype: bool
        """
        return PropertyDef.get().has_implicit_env or self.is_bound

    @property
    def is_bound(self):
        """
        Return whether Env is bound, i.e. if it can be used in the current
        context.

        :rtype: bool
        """
        return self._is_bound

    @contextmanager
    def bind(self):
        """
        Tag Env as being bound.

        This is used during the "construct" pass to check that all uses of Env
        are made in a context where it is legal.
        """
        saved_is_bound = self._is_bound
        self._is_bound = True
        yield
        self._is_bound = saved_is_bound

    def construct(self):
        check_source_language(
            self.has_ambient_env,
            'This property has no implicit environment parameter: please use'
            ' the eval_in_env construct to bind an environment first.'
        )
        return super(EnvVariable, self).construct()

    def __repr__(self):
        return '<Env>'


def env_get_repr(self):
    return '<{} {}: {}>'.format(
        (names.Name('Env') + names.Name.from_lower(self.attr_name)).camel,
        self.sub_expressions[0],
        self.sub_expressions[1],
    )


@auto_attr_custom("get", repr_fn=env_get_repr)
@auto_attr_custom("get_sequential", repr_fn=env_get_repr, sequential=True)
@auto_attr_custom("resolve_unique", repr_fn=env_get_repr, resolve_unique=True)
def env_get(env_expr, token_expr, resolve_unique=False, sequential=False):
    """
    Expression for lexical environment get operation.

    :param AbstractExpression env_expr: Expression that will yield the env
        to get the element from.
    :param AbstractExpression token_expr: Expression that will yield the
        token to use as a key on the env.
    :param bool resolve_unique: Wether we want an unique result or not.
        NOTE: For the moment, nothing will be done to ensure that only one
        result is available. The implementation will just take the first
        result.
    :param bool sequential: Whether resolution needs to be sequential or not.
    """

    sub_exprs = [construct(env_expr, LexicalEnvType),
                 construct(token_expr, Token)]

    if sequential:
        # Pass the From parameter if the user wants sequential semantics
        array_expr = 'AST_Envs.Get ({}, Get_Symbol ({}), {})'
        sub_exprs.append(construct(Self, T.root_node))
    else:
        array_expr = 'AST_Envs.Get ({}, Get_Symbol ({}))'

    make_expr = partial(BasicExpr, result_var_name="Env_Get_Result",
                        sub_exprs=sub_exprs)

    if resolve_unique:
        return make_expr("Get ({}, 0)".format(array_expr), EnvElement)
    else:
        EnvElement.array_type().add_to_context()
        return make_expr("Create ({})".format(array_expr),
                         EnvElement.array_type())


class EnvBindExpr(ResolvedExpression):

    def __init__(self, env_expr, to_eval_expr):
        self.to_eval_expr = to_eval_expr
        self.env_expr = env_expr

        # Declare a variable that will hold the value of the
        # bound environment.
        self.static_type = self.to_eval_expr.type
        self.env_var = PropertyDef.get().vars.create("New_Env",
                                                     LexicalEnvType)

        super(EnvBindExpr, self).__init__()

    def _render_pre(self):
        # First, compute the environment to bind using the current one and
        # store it in the "New_Env" local variable.
        #
        # We need to keep the environment live during the bind operation.
        # That is why we store this environment in a temporary so that it
        # is automatically deallocated when leaving the scope.
        result = (
            '{env_expr_pre}\n'
            '{env_var} := {env_expr};\n'
            'Inc_Ref ({env_var});'.format(
                env_expr_pre=self.env_expr.render_pre(),
                env_expr=self.env_expr.render_expr(),
                env_var=self.env_var.name
            )
        )

        # Then we can compute the nested expression with the bound
        # environment.
        with Env.bind_name(self.env_var.name):
            return '{}\n{}'.format(result, self.to_eval_expr.render_pre())

    def _render_expr(self):
        # We just bind the name of the environment placeholder to our
        # variable.
        with Env.bind_name(self.env_var.name):
            return self.to_eval_expr.render_expr()

    def __repr__(self):
        return '<EnvBind.Expr>'


@auto_attr
def eval_in_env(env_expr, to_eval_expr):
    """
    Expression that will evaluate a subexpression in the context of a
    particular lexical environment. Not meant to be used directly, but instead
    via the eval_in_env shortcut.

    :param AbstractExpression env_expr: An expression that will return a
        lexical environment in which we will eval to_eval_expr.
    :param AbstractExpression to_eval_expr: The expression to eval.
    """
    env_resolved_expr = construct(env_expr, LexicalEnvType)
    with Env.bind():
        return EnvBindExpr(env_resolved_expr, construct(to_eval_expr))


@auto_attr
def env_orphan(env_expr):
    """
    Expression that will create a lexical environment copy with no parent.

    :param AbstractExpression env_expr: Expression that will return a
        lexical environment.
    """
    return BuiltinCallExpr(
        'AST_Envs.Orphan',
        LexicalEnvType,
        [construct(env_expr, LexicalEnvType)],
        'Orphan_Env'
    )


class EnvGroup(AbstractExpression):
    """
    Expression that will return a lexical environment thata logically groups
    together multiple lexical environments.
    """

    def __init__(self, *env_exprs):
        super(EnvGroup, self).__init__()
        self.env_exprs = list(env_exprs)

    def construct(self):
        env_exprs = [construct(e, LexicalEnvType) for e in self.env_exprs]
        return BuiltinCallExpr(
            'Group', LexicalEnvType,
            [ArrayExpr(env_exprs, LexicalEnvType)],
            'Group_Env'
        )


@auto_attr
def env_group(env_array_expr):
    """
    Expression that will return a lexical environment that logically groups
    together multiple lexical environments from an array of lexical
    environments.

    :param AbstractExpression env_array_expr: Expression that will return
        an array of lexical environments. If this array is empty, the empty
        environment is returned.
    """
    return BuiltinCallExpr(
        'Group', LexicalEnvType,
        [construct(env_array_expr, LexicalEnvType.array_type())],
        'Group_Env'
    )


@auto_attr
def is_visible_from(referenced_env, base_env):
    """
    Expression that will return whether an env's associated compilation unit is
    visible from another env's compilation unit.

    TODO: This is mainly exposed on envs because the CompilationUnit type is
    not exposed in the DSL yet. We might want to change that eventually if
    there are other compelling reasons to do it.

    :param AbstractExpression base_env: The environment from which we want
        to check visibility.
    :param AbstractExpression referenced_env: The environment referenced
        from base_env, for which we want to check visibility.
    """
    return BuiltinCallExpr(
        'Is_Visible_From', BoolType,
        [construct(base_env, LexicalEnvType),
         construct(referenced_env, LexicalEnvType)]
    )


@auto_attr
def env_node(env):
    """
    Return the node associated to this environment.

    :param AbstractExpression env: The source environment.
    """
    return BasicExpr('{}.Node', T.root_node, [construct(env, LexicalEnvType)])


Env = EnvVariable()
EmptyEnv = AbstractVariable(names.Name("AST_Envs.Empty_Env"),
                            type=LexicalEnvType)
